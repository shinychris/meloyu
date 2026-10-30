"""市场服务（V2-c，v0.10.1）：上架/下架/浏览/购买（分账+非独占授权记录）。"""
from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
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

_ERR_ALREADY_BOUGHT = tr("已购买过该作品（非独占授权已生效）",
                         "Already purchased (non-exclusive license in effect)")


def _prefetch_listing_extras(db: Session, listings: list[MarketListing]) -> dict[str, dict]:
    """批量预取条目的销售计数与卖家昵称（列表页 N+1 → 两条附加查询）。

    返回 {listing_id: {"sales": int, "nickname": str}}。
    """
    if not listings:
        return {}
    listing_ids = [item.id for item in listings]
    sales = dict(db.execute(
        select(MarketOrder.listing_id, func.count()).where(
            MarketOrder.listing_id.in_(listing_ids)).group_by(MarketOrder.listing_id)
    ).all())
    seller_ids = {item.seller_user_id for item in listings}
    nicknames = {u.id: u.nickname for u in db.execute(
        select(User).where(User.id.in_(seller_ids))).scalars()}
    return {item.id: {"sales": int(sales.get(item.id, 0)),
                      "nickname": nicknames.get(item.seller_user_id, "")}
            for item in listings}


def listing_to_dict(db: Session, listing: MarketListing, sales: int | None = None,
                    seller_nickname: str | None = None) -> dict:
    if sales is None:
        sales = db.execute(select(func.count()).select_from(MarketOrder).where(
            MarketOrder.listing_id == listing.id)).scalar_one()
    if seller_nickname is None:
        seller = db.get(User, listing.seller_user_id)
        seller_nickname = seller.nickname if seller else ""
    return {
        "id": listing.id, "work_id": listing.work_id, "title": listing.title, "tags": listing.tags or [],
        "price_credits": listing.price_credits, "status": listing.status,
        "preview_file_id": listing.preview_file_id,
        "seller": {"user_id": listing.seller_user_id,
                   "nickname": seller_nickname},
        "sales": sales, "created_at": listing.created_at,
    }


def _require_commercial_license(db: Session, work: Work) -> None:
    """P1-2（2026-09-26）：上架售卖前置商用授权校验。

    非商用许可产物（免费档证书 / 非商用通道如社区许可模型）被平台参与
    转售=许可违约；以该作品最近一次签发证书的 license_type 为准，无证书
    或非商用一律拒绝（引导先在作品页下载商用授权证书）。
    """
    from app.models import Certificate
    cert = db.execute(select(Certificate).where(Certificate.work_id == work.id)
                      .order_by(Certificate.issued_at.desc(), Certificate.id.desc())
                      .limit(1)).scalars().first()
    if cert is None or cert.license_type != "commercial":
        raise err_conflict(tr(
            "上架售卖需商用授权：请先在作品页下载商用授权证书"
            "（免费档/非商用许可产物不可售卖）",
            "Selling requires a commercial license: download a commercial license "
            "certificate on the work page first (free-plan / non-commercial-licensed "
            "outputs cannot be sold)"))


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
    # P1-2：标题/标签过敏感词（与生成侧同库），防市场上架内容裸奔
    from app.providers.lyrics_local import check_sensitive
    if check_sensitive(f"{work.title} {' '.join(work.tags or [])}".strip()):
        from app.core.errors import err_sensitive
        raise err_sensitive()
    _require_commercial_license(db, work)
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
    listing = MarketListing(work_id=work.id, seller_user_id=user.id, title=work.title,
                      tags=work.tags or [], price_credits=int(price_credits),
                      status="active", preview_file_id=preview_fid,
                      ack_commercial=True, created_at=now, updated_at=now)
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing_to_dict(db, listing)


def delist(db: Session, user: User, listing_id: str) -> dict:
    listing = _owned_listing(db, user, listing_id)
    listing.status = "delisted"
    listing.updated_at = utc_now_iso()
    db.commit()
    return listing_to_dict(db, listing)


def admin_delist(db: Session, admin: User, listing_id: str, reason: str = "") -> dict:
    """平台治理下架（P1-2：admin 专用，违规/投诉处置入口）。

    留痕在卖家视角的 listing 状态与事件流；reason 必填口径由 API 层约束。
    """
    if not getattr(admin, "is_admin", False):
        raise err_forbidden()
    listing = db.get(MarketListing, listing_id)
    if listing is None:
        raise err_not_found(tr("市场条目不存在", "Market listing not found"))
    listing.status = "delisted"
    listing.updated_at = utc_now_iso()
    from app.models import EditEvent
    db.add(EditEvent(user_id=admin.id, work_id=listing.work_id, action="update",
                     actor="system", detail={"market_admin_delist": True,
                                             "listing_id": listing.id, "reason": reason}))
    db.commit()
    return listing_to_dict(db, listing)


def delist_for_work(db: Session, work_id: str) -> int:
    """作品被物理删除/注销清扫时联动下架（P1-1：防买家买到已删作品的空气）。

    MarketListing.work_id 无外键（历史设计），删除路径必须显式调用本函数。
    返回下架条数。
    """
    rows = db.execute(select(MarketListing).where(
        MarketListing.work_id == work_id,
        MarketListing.status == "active")).scalars().all()
    now = utc_now_iso()
    for listing in rows:
        listing.status = "delisted"
        listing.updated_at = now
    return len(rows)


def _owned_listing(db: Session, user: User, listing_id: str) -> MarketListing:
    listing = db.get(MarketListing, listing_id)
    if listing is None or listing.seller_user_id != user.id:
        raise err_not_found(tr("市场条目不存在", "Market listing not found"))
    return listing


def browse(db: Session, page: int = 1, page_size: int = 20, q: str | None = None) -> dict:
    cond = [MarketListing.status == "active"]
    if q:
        cond.append(MarketListing.title.ilike(f"%{q}%"))
    rows = db.execute(select(MarketListing).where(*cond)
                      .order_by(MarketListing.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).scalars().all()
    total = db.execute(select(func.count()).select_from(MarketListing)
                       .where(*cond)).scalar_one()
    extras = _prefetch_listing_extras(db, rows)
    items = [listing_to_dict(db, listing, sales=extras[listing.id]["sales"],
                             seller_nickname=extras[listing.id]["nickname"])
             for listing in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def _already_owned(db: Session, listing_id: str, buyer_user_id: str) -> bool:
    """该买家是否已购过该条目（非独占授权一次性；另有 uq_market_order_buyer 兜底）。"""
    return db.execute(select(MarketOrder.id).where(
        MarketOrder.listing_id == listing_id,
        MarketOrder.buyer_user_id == buyer_user_id)).first() is not None


def purchase(db: Session, user: User, listing_id: str) -> dict:
    listing = db.get(MarketListing, listing_id)
    if listing is None or listing.status != "active":
        raise err_not_found(tr("市场条目不存在或已下架", "Listing not found or delisted"))
    if listing.seller_user_id == user.id:
        raise err_conflict(tr("不能购买自己上架的作品", "Cannot buy your own listing"))
    # P1-1（2026-09-26）：作品物理删除/回收站清扫不联动下架曾使买家买到空气——
    # 成交前校验作品与试听文件仍然存在（market 表无外键，显式校验兜底）
    from app.models import File
    if db.get(Work, listing.work_id) is None or (
            listing.preview_file_id and db.get(File, listing.preview_file_id) is None):
        listing.status = "delisted"
        listing.updated_at = utc_now_iso()
        db.commit()
        raise err_not_found(tr("该作品已被卖家删除，条目已下架",
                           "The seller has deleted this work; listing delisted"))
    if _already_owned(db, listing.id, user.id):
        raise err_conflict(_ERR_ALREADY_BOUGHT)
    price = int(listing.price_credits)
    fee = int(round(price * PLATFORM_FEE_RATE))
    earnings = price - fee
    atomic_deduct(db, user.id, price, "market_purchase", None)  # 买家扣减（卖家入账=market_sale）
    # 卖家入账（正向调整直写，事务内一致）
    db.execute(
        text(
            "UPDATE users SET credit_balance = credit_balance + :amt, "
            "updated_at = :now WHERE id = :uid"),
        {"amt": earnings, "uid": listing.seller_user_id, "now": utc_now_iso()})
    from app.models import User as _U
    seller = db.get(_U, listing.seller_user_id)
    from app.models.user import CreditTransaction
    now = utc_now_iso()
    db.add(CreditTransaction(user_id=listing.seller_user_id, delta=earnings,
                             reason="market_sale", balance_after=seller.credit_balance,
                             ref_task_id=None, created_at=now))
    order = MarketOrder(listing_id=listing.id, work_id=listing.work_id, buyer_user_id=user.id,
                        seller_user_id=listing.seller_user_id, price_credits=price,
                        seller_earnings=earnings, platform_fee=fee, created_at=now)
    db.add(order)
    try:
        db.commit()
    except IntegrityError:
        # uq_market_order_buyer（listing_id, buyer_user_id）唯一兜底（2026-10-27）：
        # 上方已购校验是 check-then-act，并发 double-click 可双双通过校验各自
        # 下单双扣——冲突即回滚整体（扣款/入账/订单同事务），转 409 业务码
        db.rollback()
        raise err_conflict(_ERR_ALREADY_BOUGHT) from None
    db.refresh(order)
    return order_to_dict(order)


def listing_preview(db: Session, listing_id: str, request):
    """市场试听（v0.10.2 公开）：active 条目的 preview 文件直接流式返回。

    浏览免登录（与 GET /market/listings 同口径）；文件解析/防穿越/Range 复用
    audio_files 白名单机制。买家购买后的完整访问走订单授予的 viewer 角色。
    """
    from app.core import audio_files as af
    listing = db.get(MarketListing, listing_id)
    if listing is None or listing.status != "active" or not listing.preview_file_id:
        raise err_not_found(tr("市场条目不存在、已下架或无试听",
                           "Listing not found, delisted, or has no preview"))
    f = af.resolve_file(db, listing.preview_file_id)
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
    return {"items": [listing_to_dict(db, listing) for listing in rows], "total": len(rows)}
