"""billing 路由（P1-1，v0.7.0：Stripe checkout/订单/portal/webhook，4 接口）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.billing import CheckoutRequest
from app.services import stripe_billing as stripe_svc

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout")
def checkout(body: CheckoutRequest, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    return ok(stripe_svc.create_checkout(db, user, body.kind, body.plan, body.interval))


@router.get("/orders")
def orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(stripe_svc.list_orders(db, user))


@router.post("/portal")
def portal(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(stripe_svc.create_portal(db, user))


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe webhook（无用户鉴权：签名验签即信任来源）。"""
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    event = stripe_svc.verify_and_parse_webhook(payload, signature)
    return ok(stripe_svc.handle_webhook_event(db, event))
