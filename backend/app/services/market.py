"""市场服务（V2-c，v0.10.1）：上架/下架/浏览/购买（分账+非独占授权记录）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import err_conflict, err_forbidden, err_not_found, err_validation
from app.core.i18n import tr
from app.models import MarketListing, MarketOrder, User, Work
from app.models.base import utc_now_iso
from app.services.credits import atomic_deduct

PLATFORM_FEE_RATE = 0.10  # 平台分账 10%（卖家得 90%）

# 买家授权口径（固定双语，订单响应/详情携带）
LICENSE_NOTICE = ("非独占、不可转让的使用授权（限买家本人项目使用）；作品为 AI 辅助生成，"
                  "AIGC 署名与来源披露随产物保留；再许可或转售须另行获得卖家许可。"
                  "Non-exclusive, non-transferable usage license (buyer's own projects "
                  "only); the work is AI-assisted — AIGC attribution and disclosure are "
                  "retained; sublicensing or resale requires the seller's permission.")


def listing_to_dict(db: Session, l: MarketListing, sales: int | None = None) -> dict:
    if sales is None:
        sales = len(db.execute(select(MarketOrder.id).where(
            MarketOrder.listing_id == l.id)).all())
    seller = db.get(User, l.seller_user_id)
    return {
        "id": l.id, "work_id": l.work_id, "title": l.title, "tags": l.tags or [],
        "price_credits": l.price_credits, "status": l.status,
        "preview_file_id": l.preview_file_id,
        "seller": {"user_id": l.seller_user_id,
                   "nickname": seller.nickname if seller else ""},
        "sales": sales, "created_at": l.created_at,
    }


def publish(db: Session, user: User, work_id: str, price_credits: int) -> dict:
    work = db.get(Work, work_id)
    if work is None or work.user_id != user.id:
        raise err_not_found(tr("作品不存在", "Work not found"))
    if not work.preview_file_id:
        # v0.10.2：无采纳候选=无试听文件，上架后买家无法验货——引导先采纳
        raise err_conflict(tr("作品尚未采用候选（无试听文件），请先在作品页采纳候选再上架",
                          "No adopted candidate (missing preview); adopt a candidate on the work page before listing"))
    if not 1 <= int(price_credits) <= 100000:
        raise err_validation(tr("价格须为 1~100000 积分", "Price must be 1-100000 credits"))
    exists = db.execute(select(MarketListing).where(
        MarketListing.work_id == work_id)).scalars().first()
    if exists:
        if exists.status == "active":
            raise err_conflict(tr("作品已在架（先下架可改价重上）",
                              "Work already listed (delist first to reprice)"))
        exists.status = "active"
        exists.price_credits = int(price_credits)
        exists.title = work.title
        exists.updated_at = utc_now_iso()
        db.commit()
        return listing_to_dict(db, exists)
    preview_fid = work.preview_file_id
    now = utc_now_iso()
    l = MarketListing(work_id=work.id, seller_user_id=user.id, title=work.title,
                      tags=work.tags or [], price_credits=int(price_credits),
                      status="active", preview_file_id=preview_fid,
                      ack_commercial=True, created_at=now, updated_at=now)
    db.add(l)
    db.commit()
    db.refresh(l)
    return listing_to_dict(db, l)


def delist(db: Session, user: User, listing_id: str) -> dict:
    l = _owned_listing(db, user, listing_id)
    l.status = "delisted"
    l.updated_at = utc_now_iso()
    db.commit()
    return listing_to_dict(db, l)


def _owned_listing(db: Session, user: User, listing_id: str) -> MarketListing:
    l = db.get(MarketListing, listing_id)
    if l is None or l.seller_user_id != user.id:
        raise err_not_found(tr("市场条目不存在", "Market listing not found"))
    return l


def browse(db: Session, page: int = 1, page_size: int = 20, q: str | None = None) -> dict:
    cond = [MarketListing.status == "active"]
    if q:
        cond.append(MarketListing.title.like(f"%{q}%"))
    rows = db.execute(select(MarketListing).where(*cond)
                      .order_by(MarketListing.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).scalars().all()
    total = len(db.execute(select(MarketListing.id).where(*cond)).all())
    return {"items": [listing_to_dict(db, l) for l in rows], "total": total,
            "page": page, "page_size": page_size}


def purchase(db: Session, user: User, listing_id: str) -> dict:
    l = db.get(MarketListing, listing_id)
    if l is None or l.status != "active":
        raise err_not_found(tr("市场条目不存在或已下架", "Listing not found or delisted"))
    if l.seller_user_id == user.id:
        raise err_conflict(tr("不能购买自己上架的作品", "Cannot buy your own listing"))
    bought = db.execute(select(MarketOrder.id).where(
        MarketOrder.listing_id == l.id, MarketOrder.buyer_user_id == user.id)).first()
    if bought:
        raise err_conflict(tr("已购买过该作品（非独占授权已生效）",
                          "Already purchased (non-exclusive license in effect)"))
    price = int(l.price_credits)
    fee = int(round(price * PLATFORM_FEE_RATE))
    earnings = price - fee
    atomic_deduct(db, user.id, price, "market_purchase", None)  # 买家扣减（卖家入账=market_sale）
    # 卖家入账（正向调整直写，事务内一致）
    db.execute(
        __import__("sqlalchemy").text(
            "UPDATE users SET credit_balance = credit_balance + :amt, "
            "updated_at = :now WHERE id = :uid"),
        {"amt": earnings, "uid": l.seller_user_id, "now": utc_now_iso()})
    from app.models import User as _U
    seller = db.get(_U, l.seller_user_id)
    from app.models.user import CreditTransaction
    now = utc_now_iso()
    db.add(CreditTransaction(user_id=l.seller_user_id, delta=earnings,
                             reason="market_sale", balance_after=seller.credit_balance,
                             ref_task_id=None, created_at=now))
    order = MarketOrder(listing_id=l.id, work_id=l.work_id, buyer_user_id=user.id,
                        seller_user_id=l.seller_user_id, price_credits=price,
                        seller_earnings=earnings, platform_fee=fee, created_at=now)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order_to_dict(order)


def listing_preview(db: Session, listing_id: str, request):
    """市场试听（v0.10.2 公开）：active 条目的 preview 文件直接流式返回。

    浏览免登录（与 GET /market/listings 同口径）；文件解析/防穿越/Range 复用
    audio_files 白名单机制。买家购买后的完整访问走订单授予的 viewer 角色。
    """
    from app.core import audio_files as af
    l = db.get(MarketListing, listing_id)
    if l is None or l.status != "active" or not l.preview_file_id:
        raise err_not_found(tr("市场条目不存在、已下架或无试听",
                           "Listing not found, delisted, or has no preview"))
    f = af.resolve_file(db, l.preview_file_id)
    return af.file_stream_response(request, f)


def order_to_dict(o: MarketOrder) -> dict:
    return {
        "id": o.id, "listing_id": o.listing_id, "work_id": o.work_id,
        "buyer_user_id": o.buyer_user_id, "seller_user_id": o.seller_user_id,
        "price_credits": o.price_credits, "seller_earnings": o.seller_earnings,
        "platform_fee": o.platform_fee, "created_at": o.created_at,
        "license": LICENSE_NOTICE,
    }


def my_orders(db: Session, user: User) -> dict:
    rows = db.execute(select(MarketOrder).where(
        MarketOrder.buyer_user_id == user.id)
        .order_by(MarketOrder.created_at.desc())).scalars().all()
    return {"items": [order_to_dict(o) for o in rows], "total": len(rows)}


def my_listings(db: Session, user: User) -> dict:
    rows = db.execute(select(MarketListing).where(
        MarketListing.seller_user_id == user.id)
        .order_by(MarketListing.created_at.desc())).scalars().all()
    return {"items": [listing_to_dict(db, l) for l in rows], "total": len(rows)}
