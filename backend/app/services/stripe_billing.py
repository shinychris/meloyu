"""Stripe 支付集成（P1-1，D-2 决策：海外市场 + Stripe）。

流程：
- 前端 POST /billing/checkout → 创建 Stripe Checkout Session（订阅或积分充值包）
  → 返回 hosted page url，用户支付；
- Stripe webhook（POST /billing/webhook，签名验签）：
  checkout.session.completed → 订单 paid + 订阅激活/积分发放；
  invoice.paid（订阅续期）→ 发放当月积分；
  customer.subscription.deleted → 降级 free；
  charge.refunded → 订单 refunded + 扣回积分（余额不足扣至 0）；
- 用户侧订单列表 GET /billing/orders；订阅管理 POST /billing/portal（Customer Portal）。

未配置 STRIPE_SECRET_KEY 时：付费功能整体不可用（付费档无法订阅/充值），
即 P0-4 止血——绝无"免费自选付费档"路径。
幂等：orders.stripe_checkout_id 唯一 + stripe_event_id 去重（webhook 重放安全）。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import err_conflict, err_validation
from app.core.i18n import tr
from app.core.logging import logger
from app.models import Order, Plan, Subscription, User
from app.models.base import utc_now_iso
from app.services import credits as credits_svc
from app.services import works as works_svc

# 已处理过的 webhook 事件（进程内幂等缓存；orders.stripe_event_id 为持久层去重）
_seen_events: set[str] = set()

_SUBSCRIPTION_PLANS = ("pro", "studio")
_INTERVALS = ("monthly", "yearly")


def stripe_enabled() -> bool:
    return bool(settings.stripe_secret_key)


def _require_stripe() -> None:
    if not stripe_enabled():
        raise err_conflict(tr(
            "支付未配置（缺少 STRIPE_SECRET_KEY），付费档暂不可用，请联系管理员",
            "Payments are not configured (missing STRIPE_SECRET_KEY); "
            "paid plans are unavailable. Please contact the administrator."))


def _price_id(plan: str, interval: str) -> str:
    mapping = {
        ("pro", "monthly"): settings.stripe_price_pro_monthly,
        ("pro", "yearly"): settings.stripe_price_pro_yearly,
        ("studio", "monthly"): settings.stripe_price_studio_monthly,
        ("studio", "yearly"): settings.stripe_price_studio_yearly,
    }
    price = mapping.get((plan, interval), "")
    if not price:
        raise err_conflict(tr(
            f"该档位/周期未配置价格（{plan}/{interval}），请联系管理员",
            f"No price configured for this plan/interval ({plan}/{interval}); "
            f"please contact the administrator."))
    return price


def create_checkout(db: Session, user: User, kind: str, plan: str | None = None,
                    interval: str | None = None) -> dict:
    """创建 Checkout Session 并落 pending 订单；返回 {url, order_id}。"""
    import stripe

    _require_stripe()
    stripe.api_key = settings.stripe_secret_key
    now = utc_now_iso()

    if kind == "subscription":
        if plan not in _SUBSCRIPTION_PLANS or interval not in _INTERVALS:
            raise err_validation(tr(
                "订阅需指定 plan=pro/studio 与 interval=monthly/yearly",
                "Subscriptions require plan=pro/studio and interval=monthly/yearly"))
        amount_hint = 0
        if plan == "pro":
            plan_row = db.get(Plan, "pro")
            amount_hint = (plan_row.price_yearly if interval == "yearly"
                           else plan_row.price_monthly) or 0
        else:
            plan_row = db.get(Plan, "studio")
            amount_hint = (plan_row.price_yearly if interval == "yearly"
                           else plan_row.price_monthly) or 0
        order = Order(user_id=user.id, kind="subscription", plan=plan, interval=interval,
                      credits=0, amount_usd=amount_hint, status="pending",
                      created_at=now, updated_at=now)
        db.add(order)
        db.flush()
        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": _price_id(plan, interval), "quantity": 1}],
                customer_email=user.email,
                client_reference_id=order.id,
                metadata={"order_id": order.id, "user_id": user.id, "kind": kind,
                          "plan": plan, "interval": interval},
                success_url=(f"{settings.app_base_url}/#/billing/return"
                             f"?status=success&session_id={{CHECKOUT_SESSION_ID}}"),
                cancel_url=f"{settings.app_base_url}/#/billing/return?status=cancel",
            )
        except Exception as e:  # noqa: BLE001
            order.status = "failed"
            db.commit()
            raise err_conflict(tr("创建支付会话失败：", "Failed to create checkout session: ")
                               + str(e)) from e
    elif kind == "topup":
        order = Order(user_id=user.id, kind="topup", credits=settings.stripe_topup_credits,
                      amount_usd=settings.stripe_topup_amount_usd, status="pending",
                      created_at=now, updated_at=now)
        db.add(order)
        db.flush()
        line_item = ({"price": settings.stripe_topup_price, "quantity": 1}
                     if settings.stripe_topup_price else
                     {"price_data": {
                         "currency": "usd",
                         "unit_amount": settings.stripe_topup_amount_usd,
                         "product_data": {"name": f"Meloyu credits x{settings.stripe_topup_credits}"},
                     }, "quantity": 1})
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[line_item],
                customer_email=user.email,
                client_reference_id=order.id,
                metadata={"order_id": order.id, "user_id": user.id, "kind": kind,
                          "credits": str(settings.stripe_topup_credits)},
                success_url=(f"{settings.app_base_url}/#/billing/return"
                             f"?status=success&session_id={{CHECKOUT_SESSION_ID}}"),
                cancel_url=f"{settings.app_base_url}/#/billing/return?status=cancel",
            )
        except Exception as e:  # noqa: BLE001
            order.status = "failed"
            db.commit()
            raise err_conflict(tr("创建支付会话失败：", "Failed to create checkout session: ")
                               + str(e)) from e
    else:
        raise err_validation(tr("kind 必须为 subscription/topup",
                                "kind must be subscription/topup"))

    order.stripe_checkout_id = session.id
    db.commit()
    return {"url": session.url, "order_id": order.id}


def list_orders(db: Session, user: User) -> dict:
    rows = db.execute(select(Order).where(Order.user_id == user.id)
                      .order_by(Order.created_at.desc()).limit(50)).scalars().all()
    return {"orders": [r.to_dict() for r in rows]}


def create_portal(db: Session, user: User) -> dict:
    """Customer Portal（管理订阅/取消/换支付方式）；需先有过支付记录（Stripe customer）。"""
    import stripe

    _require_stripe()
    stripe.api_key = settings.stripe_secret_key
    customer_id = db.execute(
        select(Order.stripe_customer_id).where(
            Order.user_id == user.id, Order.stripe_customer_id.isnot(None))
        .order_by(Order.created_at.desc()).limit(1)).scalar_one_or_none()
    if not customer_id:
        raise err_conflict(tr(
            "尚无支付记录，无法打开订阅管理门户",
            "No payment records yet; the subscription portal is unavailable"))
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{settings.app_base_url}/#/pricing",
    )
    return {"url": session.url}


# ---- webhook 处理 ----


def verify_and_parse_webhook(payload: bytes, signature: str) -> dict:
    """验签并解析事件；签名不合法抛 40001。"""
    import stripe

    if not stripe_enabled() or not settings.stripe_webhook_secret:
        raise err_validation(tr("webhook 未配置", "webhook is not configured"))
    stripe.api_key = settings.stripe_secret_key
    try:
        event = stripe.Webhook.construct_event(
            payload, signature or "", settings.stripe_webhook_secret)
    except Exception as e:  # noqa: BLE001
        raise err_validation(tr("webhook 签名校验失败", "webhook signature verification failed")
                             ) from e
    # stripe.Event → dict（后续处理链统一 dict 访问，便于测试与序列化）
    return event.to_dict() if hasattr(event, "to_dict") else event


def handle_webhook_event(db: Session, event: dict) -> dict:
    """事件分发（幂等：stripe_event_id 去重）。"""
    event_id = str(event.get("id") or "")
    etype = str(event.get("type") or "")
    if event_id and (event_id in _seen_events or _event_processed(db, event_id)):
        return {"received": True, "duplicate": True}
    data = (event.get("data") or {}).get("object") or {}
    try:
        if etype == "checkout.session.completed":
            _on_checkout_completed(db, data)
        elif etype == "invoice.paid":
            _on_invoice_paid(db, data)
        elif etype == "customer.subscription.deleted":
            _on_subscription_deleted(db, data)
        elif etype == "charge.refunded":
            _on_charge_refunded(db, data)
        else:
            logger.info(f"stripe webhook ignored: {etype}")
    finally:
        if event_id:
            _seen_events.add(event_id)
            if len(_seen_events) > 1000:
                _seen_events.clear()
    return {"received": True}


def _event_processed(db: Session, event_id: str) -> bool:
    return db.execute(select(Order.id).where(
        Order.stripe_event_id == event_id).limit(1)).first() is not None


def _mark_event(db: Session, order: Order, event: dict) -> None:
    order.stripe_event_id = str(event.get("id") or "") or order.stripe_event_id


def _order_by_checkout(db: Session, session_id: str) -> Order | None:
    if not session_id:
        return None
    return db.execute(select(Order).where(
        Order.stripe_checkout_id == session_id)).scalars().first()


def _on_checkout_completed(db: Session, data: dict) -> None:
    order = _order_by_checkout(db, data.get("id") or "")
    if order is None:
        # metadata 兜底（老订单/手工创建）
        meta = data.get("metadata") or {}
        oid = meta.get("order_id")
        order = db.get(Order, oid) if oid else None
        if order is None:
            logger.warning(f"stripe checkout.completed: no order for session {data.get('id')}")
            return
    if order.status == "paid":
        return  # 幂等
    now = utc_now_iso()
    order.status = "paid"
    order.paid_at = now
    order.stripe_customer_id = data.get("customer") or order.stripe_customer_id
    order.stripe_subscription_id = (data.get("subscription")
                                    or order.stripe_subscription_id)
    if order.kind == "topup":
        user = db.get(User, order.user_id)
        credits_svc.grant(db, user, order.credits, "topup")
    else:
        _activate_plan(db, db.get(User, order.user_id), order.plan or "pro")
    works_svc.add_event(db, user_id=order.user_id, action="plan_switch", actor="system",
                        detail={"order": order.id, "kind": order.kind, "via": "stripe",
                                "plan": order.plan, "credits": order.credits})
    db.commit()
    logger.info(f"stripe order {order.id} paid ({order.kind})")


def _on_invoice_paid(db: Session, data: dict) -> None:
    """订阅续期（周期发票支付成功）→ 发放当月积分。"""
    sub_id = data.get("subscription") or ""
    if not sub_id:
        return
    order = db.execute(select(Order).where(
        Order.stripe_subscription_id == sub_id,
        Order.kind == "subscription", Order.status == "paid")
        .order_by(Order.created_at.desc()).limit(1)).scalars().first()
    if order is None:
        return
    user = db.get(User, order.user_id)
    if user is None or user.plan != order.plan:
        return  # 已降级/换档，续期积分随激活流程发放
    plan_row = db.get(Plan, order.plan)
    if plan_row and plan_row.monthly_credits:
        credits_svc.grant(db, user, plan_row.monthly_credits, "plan_grant",
                          set_carry_over=True)
    db.commit()
    logger.info(f"stripe invoice.paid: monthly credits granted to user {user.id}")


def _on_subscription_deleted(db: Session, data: dict) -> None:
    sub_id = data.get("id") or ""
    order = db.execute(select(Order).where(
        Order.stripe_subscription_id == sub_id,
        Order.kind == "subscription", Order.status == "paid")
        .order_by(Order.created_at.desc()).limit(1)).scalars().first()
    if order is None:
        return
    user = db.get(User, order.user_id)
    if user is None:
        return
    now = utc_now_iso()
    rows = db.execute(select(Subscription).where(
        Subscription.user_id == user.id, Subscription.status == "active")).scalars().all()
    for row in rows:
        row.status = "canceled"
        row.ended_at = now
    user.plan = "free"
    user.credit_monthly_grant = 0
    user.credit_next_grant_at = None
    user.updated_at = now
    works_svc.add_event(db, user_id=user.id, action="plan_switch", actor="system",
                        detail={"to": "free", "reason": "stripe_subscription_deleted"})
    db.commit()
    logger.info(f"stripe subscription deleted: user {user.id} downgraded to free")


def _on_charge_refunded(db: Session, data: dict) -> None:
    session_id = ((data.get("metadata") or {}).get("checkout_session_id")
                  or "")
    order = _order_by_checkout(db, session_id)
    if order is None:
        # charge 对象无 checkout 元数据时按金额最近匹配兜底
        amount = int(data.get("amount_refunded") or 0)
        if amount <= 0:
            return
        order = db.execute(select(Order).where(
            Order.user_id == (data.get("metadata") or {}).get("user_id") or "",
            Order.amount_usd == amount, Order.status == "paid")
            .order_by(Order.created_at.desc()).limit(1)).scalars().first()
        if order is None:
            return
    if order.status == "refunded":
        return
    user = db.get(User, order.user_id)
    if user is None:
        return
    if order.kind == "topup" and order.credits:
        credits_svc.deduct_refund(db, user, order.credits)
    order.status = "refunded"
    order.updated_at = utc_now_iso()
    db.commit()
    logger.info(f"stripe order {order.id} refunded")


def _activate_plan(db: Session, user: User | None, plan_code: str) -> None:
    """支付确认后的订阅激活（与 billing.switch_plan 同语义，source=stripe）。"""
    if user is None:
        return
    from app.services.billing import _next_month_first
    now = utc_now_iso()
    old_rows = db.execute(select(Subscription).where(
        Subscription.user_id == user.id, Subscription.status == "active")).scalars().all()
    for row in old_rows:
        row.status = "canceled"
        row.ended_at = now
    plan = db.get(Plan, plan_code)
    granted = plan.monthly_credits if plan and plan.monthly_credits else 0
    db.add(Subscription(user_id=user.id, plan=plan_code, status="active", started_at=now,
                        source="stripe", granted_credits=granted,
                        created_at=now, updated_at=now))
    user.plan = plan_code
    db.flush()
    if granted > 0:
        credits_svc.grant(db, user, granted, "plan_grant", set_carry_over=True)
        user.credit_monthly_grant = granted
        user.credit_next_grant_at = _next_month_first()
    else:
        user.credit_monthly_grant = 0
        user.credit_next_grant_at = None
    user.updated_at = now
