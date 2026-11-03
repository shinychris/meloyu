"""作品市场路由（v0.10.1；v0.10.2 增公开试听）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.services import market as market_svc

router = APIRouter(prefix="/market", tags=["market"])


class PublishRequest(BaseModel):
    work_id: str = Field(min_length=32, max_length=32)
    price_credits: int = Field(ge=1, le=100000)


class AdminDelistRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=200)


@router.post("/listings", status_code=201)
def publish(body: PublishRequest, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    """上架（属主；上架即确认持有商用授权，合规留痕）。"""
    return ok(market_svc.publish(db, user, body.work_id, body.price_credits),
              status_code=201)


@router.delete("/listings/{listing_id}")
def delist(listing_id: str, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    return ok(market_svc.delist(db, user, listing_id))


@router.get("/listings/{listing_id}/preview")
def listing_preview(listing_id: str, request: Request,
                    db: Session = Depends(get_db)):
    """市场试听（v0.10.2 公开）：active 条目 preview 流式播放，免鉴权可 Range。"""
    return market_svc.listing_preview(db, listing_id, request)


@router.get("/listings")
def browse(page: int = Query(default=1, ge=1),
           page_size: int = Query(default=20, ge=1, le=100),
           q: str = Query(default="", max_length=50),
           db: Session = Depends(get_db)):
    """市场浏览（无需登录即可看，购买需鉴权）。"""
    return ok(market_svc.browse(db, page, page_size, q or None))


@router.post("/listings/{listing_id}/purchase")
def purchase(listing_id: str, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """购买（积分原子扣减；卖家 90% / 平台 10% 分账；非独占授权订单凭证）。"""
    return ok(market_svc.purchase(db, user, listing_id))


@router.get("/my/listings")
def my_listings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(market_svc.my_listings(db, user))


@router.get("/my/orders")
def my_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(market_svc.my_orders(db, user))


@router.post("/admin/listings/{listing_id}/delist")
def admin_delist(listing_id: str, body: AdminDelistRequest,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """平台治理下架（admin； 违规/投诉处置入口）。"""
    return ok(market_svc.admin_delist(db, user, listing_id, body.reason))
