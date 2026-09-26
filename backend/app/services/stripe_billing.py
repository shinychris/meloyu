"""Stripe 支付集成（P1-1，D-2 决策：海外市场 + Stripe）。

流程：
- 前端 POST /billing/checkout → 创建 Stripe Checkout Session（订阅或积分充值包）
  → 返回 hosted page url，用户支付；
- Stripe webhook（POST /billing/webhook，签名验签）：
  checkout.session.completed → 订单 paid（回填真实金额/币种）+ 订阅激活/积分发放
    + 取消该用户旧 Stripe 订阅（防双订阅双扣）；
  invoice.paid（billing_reason=subscription_cycle）→ 续期发放当月积分；
  invoice.payment_failed → dunning 留痕 + 尽力催付邮件（积分发放已被单时钟冻结）；
  customer.subscription.updated → 换档同步（price→plan 映射）/取消态降级/past_due 留痕；
  customer.subscription.deleted → 降级 free（仅当删的是当前生效订阅）；
  charge.refunded → 订单 refunded + 扣回积分；订阅退款加降级与月度积分追回；
- 用户侧订单列表 GET /billing/orders；订阅管理 POST /billing/portal（Customer Portal）。

未配置 STRIPE_SECRET_KEY 时：付费功能整体不可用（付费档无法订阅/充值），
即 P0-4 止血——绝无"免费自选付费档"路径。

幂等与单时钟（2026-09-26 商业化审查 P0-1/P0-2 修复）：
- 持久化幂等：stripe_events 表（处理成功同事务落表；异常绝不落表并 5xx
  交 Stripe 重试）。原进程内 set 重启失忆、异常仍标已处理的两处资金缺陷移除。
- 单时钟：Stripe 订阅用户的本地月度水位（credit_next_grant_at）一律不武装
  （None），月度积分只由 invoice.paid 续期发票驱动；本地惰性时钟仅服务
  非 Stripe 来源（历史/运营手工）。原双时钟并存导致订阅用户每月双倍积分。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import err_conflict, err_validation
from app.core.i18n import tr
from app.core.logging import logger
from app.models import Order, Plan, StripeEvent, Subscription, User
from app.models.base import utc_now_iso
from app.services import credits as credits_svc
from app.services import works as works_svc

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
    mapping = _price_map()
    price = mapping.get((plan, interval), "")
    if not price:
        raise err_conflict(tr(
            f"该档位/周期未配置价格（{plan}/{interval}），请联系管理员",
            f"No price configured for this plan/interval ({plan}/{interval}); "
            f"please contact the administrator."))
    return price


def _price_map() -> dict[tuple[str, str], str]:
    return {
        ("pro", "monthly"): settings.stripe_price_pro_monthly,
        ("pro", "yearly"): settings.stripe_price_pro_yearly,
        ("studio", "monthly"): settings.stripe_price_studio_monthly,
        ("studio", "yearly"): settings.stripe_price_studio_yearly,
    }


def _plan_from_price(price_id: str) -> tuple[str, str] | None:
    """Stripe price id → (plan, interval)；未配置映射或未知价格返回 None。"""
    for (plan, interval), pid in _price_map().items():
        if pid and price_id == pid:
            return plan, interval
    return None


def create_checkout(db: Session, user: User, kind: str, plan: str | None = None,
                    interval: str | None = None) -> dict:
    """创建 Checkout Session 并落 pending 订单；返回 {url, order_id}。

    订单金额先记 Plan 表 USD 分值提示（hint）；支付确认后由 webhook 按
    Checkout Session 的 amount_total/currency 回填真实值（P0-5：价格口径
    全 USD，orders 金额可与 Stripe 对账单核对）。
    billing_address_collection=auto（P1-6）：B2B 客户可留账单地址，
    为 Stripe Tax / 发票开具备好前提。
    """
    import stripe

    _require_stripe()
    stripe.api_key = settings.stripe_secret_key
    now = utc_now_iso()

    if kind == "subscription":
        if plan not in _SUBSCRIPTION_PLANS or interval not in _INTERVALS:
            raise err_validation(tr(
                "订阅需指定 plan=pro/studio 与 interval=monthly/yearly",
                "Subscriptions require plan=pro/studio and interval=monthly/yearly"))
        plan_row = db.get(Plan, plan or "pro")
        amount_hint = ((plan_row.price_yearly if interval == "yearly"
                        else plan_row.price_monthly) if plan_row else 0) or 0
        order = Order(user_id=user.id, kind="subscription", plan=plan, interval=interval,
                      credits=0, amount_usd=amount_hint, currency="usd", status="pending",
                      created_at=now, updated_at=now)
        db.add(order)
        db.flush()
        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": _price_id(plan, interval), "quantity": 1}],
                customer_email=user.email,
                client_reference_id=order.id,
                billing_address_collection="auto",
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
                      amount_usd=settings.stripe_topup_amount_usd, currency="usd",
                      status="pending", created_at=now, updated_at=now)
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
                billing_address_collection="auto",
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
        # 安审计 L-3（2026-09-09）：对外错误口径与验签失败一致，不泄露
        # "支付通道是否已配置"这一内部状态；真实原因只进服务端日志
        logger.warning("stripe webhook called but not configured "
                       "(STRIPE_SECRET_KEY/STRIPE_WEBHOOK_SECRET missing)")
        raise err_validation(tr("webhook 请求被拒绝", "webhook request rejected"))
    stripe.api_key = settings.stripe_secret_key
    try:
        event = stripe.Webhook.construct_event(
            payload, signature or "", settings.stripe_webhook_secret)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"stripe webhook signature verification failed: {e.__class__.__name__}")
        raise err_validation(tr("webhook 请求被拒绝", "webhook request rejected")) from e
    # stripe.Event → dict（后续处理链统一 dict 访问，便于测试与序列化）
    return event.to_dict() if hasattr(event, "to_dict") else event


def handle_webhook_event(db: Session, event: dict) -> dict:
    """事件分发（持久化幂等：stripe_events 表；异常不吞，5xx 交 Stripe 重试）。

    事务边界：各 handler 只 flush 不 commit；处理成功后本函数把 StripeEvent
    标记与业务变更**同一事务**提交——commit 失败则标记一并回滚，Stripe 重试
    整个事件（at-least-once，各 handler 内部自带业务幂等护栏）。
    """
    event_id = str(event.get("id") or "")
    etype = str(event.get("type") or "")
    if event_id and _event_processed(db, event_id):
        return {"received": True, "duplicate": True}
    data = (event.get("data") or {}).get("object") or {}
    try:
        if etype == "checkout.session.completed":
            _on_checkout_completed(db, data)
        elif etype == "invoice.paid":
            _on_invoice_paid(db, data)
        elif etype == "invoice.payment_failed":
            _on_payment_failed(db, data)
        elif etype == "customer.subscription.updated":
            _on_subscription_updated(db, data)
        elif etype == "customer.subscription.deleted":
            _on_subscription_deleted(db, data)
        elif etype == "charge.refunded":
            _on_charge_refunded(db, data)
        else:
            logger.info(f"stripe webhook ignored: {etype}")
    except Exception:
        # 关键（P0-2）：异常绝不落事件标记——返回 5xx 让 Stripe 重试，
        # 修复原实现 finally 无条件标记导致的"收款不发货"静默丢单
        db.rollback()
        raise
    if event_id:
        db.add(StripeEvent(event_id=event_id, type=etype, processed_at=utc_now_iso()))
    db.commit()
    return {"received": True}


def _event_processed(db: Session, event_id: str) -> bool:
    return db.get(StripeEvent, event_id) is not None


def _order_by_checkout(db: Session, session_id: str) -> Order | None:
    if not session_id:
        return None
    return db.execute(select(Order).where(
        Order.stripe_checkout_id == session_id)).scalars().first()


def _latest_sub_order(db: Session, user_id: str) -> Order | None:
    """该用户最近一笔已支付的订阅订单（当前生效订阅的归属依据）。"""
    return db.execute(select(Order).where(
        Order.user_id == user_id, Order.kind == "subscription", Order.status == "paid")
        .order_by(Order.created_at.desc(), Order.id.desc()).limit(1)).scalars().first()


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
    # P0-5：回填 Stripe 实收金额/币种（覆盖 Plan 表 hint；可对账）
    amount_total = data.get("amount_total")
    if isinstance(amount_total, int) and amount_total > 0:
        order.amount_usd = amount_total
    order.currency = str(data.get("currency") or order.currency or "usd")
    if order.kind == "topup":
        user = db.get(User, order.user_id)
        credits_svc.grant(db, user, order.credits, "topup")
    else:
        user = db.get(User, order.user_id)
        _cancel_other_stripe_subscriptions(db, user, order)
        _activate_plan(db, user, order.plan or "pro",
                       stripe_subscription_id=order.stripe_subscription_id)
    works_svc.add_event(db, user_id=order.user_id, action="plan_switch", actor="system",
                        detail={"order": order.id, "kind": order.kind, "via": "stripe",
                                "plan": order.plan, "credits": order.credits})
    db.flush()
    logger.info(f"stripe order {order.id} paid ({order.kind})")


def _cancel_other_stripe_subscriptions(db: Session, user: User | None,
                                       current_order: Order) -> None:
    """P1-4：新订阅激活时取消该用户其余 Stripe 订阅（防再次 checkout 升级
    造成的双订阅双扣款）。换档推荐走 Customer Portal（subscription.updated
    同步换档），此为兜底。取消失败只告警不阻断激活。"""
    if user is None:
        return
    rows = db.execute(select(Order.stripe_subscription_id).where(
        Order.user_id == user.id, Order.kind == "subscription", Order.status == "paid",
        Order.stripe_subscription_id.isnot(None)).distinct()).scalars().all()
    stale = [sid for sid in rows if sid and sid != current_order.stripe_subscription_id]
    if not stale:
        return
    import stripe

    if not stripe_enabled():
        return
    stripe.api_key = settings.stripe_secret_key
    for sid in stale:
        try:
            stripe.Subscription.cancel(sid)
            logger.info(f"cancelled stale stripe subscription {sid} for user {user.id}")
        except Exception as e:  # noqa: BLE001 —— 已被取消/不可达不阻断激活
            logger.warning(f"failed to cancel stale stripe subscription {sid}: "
                           f"{e.__class__.__name__}")


def _on_invoice_paid(db: Session, data: dict) -> None:
    """订阅发票支付成功 → 按发票类型分流（P0-1 单时钟的核心）。

    - subscription_cycle（续期）：发放当月积分（Stripe 订阅用户唯一的月度发放来源）；
    - subscription_create（首期）：积分已在 checkout.completed 激活时发放，跳过；
    - 其他（subscription_update 换档按比例发票等）：发放归 subscription.updated
      换档处理器（一次性发放新档位积分），此处跳过防双发。
    """
    sub_id = data.get("subscription") or ""
    if not sub_id:
        return
    if str(data.get("billing_reason") or "") != "subscription_cycle":
        logger.info(f"stripe invoice.paid skipped (billing_reason="
                    f"{data.get('billing_reason')}): no grant")
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
        user.credit_monthly_grant = plan_row.monthly_credits
        # 单时钟（P0-1）：Stripe 订阅用户本地水位保持未武装
        user.credit_next_grant_at = None
    db.flush()
    logger.info(f"stripe invoice.paid: monthly credits granted to user {user.id}")


def _on_payment_failed(db: Session, data: dict) -> None:
    """续费扣款失败（dunning 起点官方口径：P0-3）。

    积分发放已被单时钟冻结（本地水位 None，invoice.paid 不会再来直到扣款
    成功），此处留痕 + 尽力催付邮件；Stripe 智能重试期内权益保留（行业惯例
    宽限），重试耗尽后 subscription.deleted 事件降级。
    """
    sub_id = data.get("subscription") or ""
    order = None
    if sub_id:
        order = db.execute(select(Order).where(
            Order.stripe_subscription_id == sub_id,
            Order.kind == "subscription", Order.status == "paid")
            .order_by(Order.created_at.desc()).limit(1)).scalars().first()
    user = db.get(User, order.user_id) if order else None
    logger.warning(f"stripe invoice.payment_failed (sub={sub_id or 'n/a'}, "
                   f"user={user.id if user else 'unknown'}): dunning started")
    if user is None:
        return
    works_svc.add_event(db, user_id=user.id, action="payment_failed", actor="system",
                        detail={"subscription": sub_id,
                                "attempt": data.get("attempt_count"),
                                "next_retry": data.get("next_payment_attempt")})
    db.flush()
    # 催付邮件尽力而为：SMTP 未配/发送失败不影响 webhook 确认
    try:
        from app.services import mail as mail_svc
        if mail_svc.smtp_configured():
            mail_svc.send_raw(
                user.email,
                "Meloyu subscription payment failed / 订阅扣款失败",
                "Your subscription payment failed. Stripe will retry automatically;\n"
                "please update your payment method in the billing portal to keep "
                "your plan active.\n\n订阅扣款失败，Stripe 将自动重试；请到订阅管理"
                "门户更新支付方式以保留档位权益。")
    except Exception as e:  # noqa: BLE001 —— 邮件失败不阻断 webhook
        logger.warning(f"dunning email failed for user {user.id}: {e.__class__.__name__}")


def _on_subscription_updated(db: Session, data: dict) -> None:
    """订阅状态/档位变更同步（P0-3/P1-4：Portal 换档、past_due、取消）。

    - status=canceled → 降级 free（同 deleted 语义）；
    - price 变化且仍 active → 换档激活（一次性发放新档位积分；此后续期走
      invoice.paid），并取消其余旧订阅；
    - past_due/unpaid → 留痕（发放已由单时钟冻结），不再额外处置。
    """
    sub_id = data.get("id") or ""
    status = str(data.get("status") or "")
    order = db.execute(select(Order).where(
        Order.stripe_subscription_id == sub_id,
        Order.kind == "subscription", Order.status == "paid")
        .order_by(Order.created_at.desc()).limit(1)).scalars().first()
    if order is None:
        return
    user = db.get(User, order.user_id)
    if user is None:
        return
    if status == "canceled":
        _downgrade_to_free(db, user, "stripe_subscription_canceled")
        return
    if status in ("past_due", "unpaid"):
        works_svc.add_event(db, user_id=user.id, action="subscription_past_due",
                            actor="system", detail={"subscription": sub_id,
                                                    "status": status})
        db.flush()
        logger.warning(f"stripe subscription {sub_id} {status} (user {user.id}); "
                       "monthly grants frozen by single-clock design")
        return
    if status != "active":
        return
    # 换档检测：subscription items 的 price → (plan, interval)
    items = ((data.get("items") or {}).get("data")) or []
    new_plan = None
    for item in items:
        price_id = str(((item.get("price") or {}).get("id")) or "")
        mapped = _plan_from_price(price_id)
        if mapped:
            new_plan = mapped[0]
            break
    if new_plan is None or new_plan == user.plan:
        return  # 未换档（如仅换支付方式/数量）或价格映射未配置
    order.plan = new_plan
    order.updated_at = utc_now_iso()
    _activate_plan(db, user, new_plan,
                   stripe_subscription_id=order.stripe_subscription_id)
    logger.info(f"stripe subscription updated: user {user.id} -> {new_plan}")


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
    # 删的是否当前生效订阅：优先按 active Subscription 行记录的 stripe id 精确
    # 判断；旧数据（列空）回退"最近 paid 订单"启发式——用户重新订阅后，旧订阅
    # 的删除事件不应把新档位降级
    active = db.execute(select(Subscription).where(
        Subscription.user_id == user.id, Subscription.status == "active",
        Subscription.source == "stripe")).scalars().first()
    if active is not None and active.stripe_subscription_id:
        if active.stripe_subscription_id != sub_id:
            logger.info(f"stripe subscription deleted: {sub_id} is not the current "
                        f"subscription of user {user.id}; skip downgrade")
            return
    else:
        latest = _latest_sub_order(db, user.id)
        if latest is not None and latest.stripe_subscription_id not in (None, sub_id):
            logger.info(f"stripe subscription deleted: {sub_id} is not the current "
                        f"subscription of user {user.id}; skip downgrade (heuristic)")
            return
    _downgrade_to_free(db, user, "stripe_subscription_deleted")


def _downgrade_to_free(db: Session, user: User, reason: str) -> None:
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
                        detail={"to": "free", "reason": reason})
    db.flush()
    logger.info(f"stripe {reason}: user {user.id} downgraded to free")


def _on_charge_refunded(db: Session, data: dict) -> None:
    """退款撤权益（P1-5）：充值扣回积分；订阅退款降级+追回当期积分。"""
    meta = data.get("metadata") or {}
    order = _order_by_checkout(db, str(meta.get("checkout_session_id") or ""))
    if order is None:
        # checkout 元数据缺失时按 order_id（我们写入 charge 元数据的键）直查
        oid = meta.get("order_id")
        order = db.get(Order, oid) if oid else None
    if order is None:
        # 最后兜底：同用户同金额的最近 paid 订单（Stripe 金额恒为实收口径）
        amount = int(data.get("amount_refunded") or 0)
        if amount <= 0:
            return
        order = db.execute(select(Order).where(
            Order.user_id == meta.get("user_id") or "",
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
    elif order.kind == "subscription":
        # 订阅退款：降级 + 追回当期已发积分（余额不足扣至 0）
        plan_row = db.get(Plan, order.plan or "")
        if plan_row and plan_row.monthly_credits:
            credits_svc.deduct_refund(db, user, plan_row.monthly_credits)
        _downgrade_to_free(db, user, "stripe_charge_refunded")
    order.status = "refunded"
    order.updated_at = utc_now_iso()
    db.flush()
    logger.info(f"stripe order {order.id} refunded")


def _activate_plan(db: Session, user: User | None, plan_code: str,
                   stripe_subscription_id: str | None = None) -> None:
    """支付确认后的订阅激活（source=stripe；单时钟：本地月度水位不武装）。

    首期积分在此发放；此后每月由 invoice.paid(billing_reason=
    subscription_cycle) 发放——两条路径互斥，杜绝双发（P0-1）。
    stripe_subscription_id 落 Subscription 行：订阅删除事件据此精确判断
    "删的是否当前生效订阅"（秒级订单序不可靠）。
    """
    if user is None:
        return
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
                        stripe_subscription_id=stripe_subscription_id,
                        created_at=now, updated_at=now))
    user.plan = plan_code
    db.flush()
    if granted > 0:
        credits_svc.grant(db, user, granted, "plan_grant", set_carry_over=True)
        user.credit_monthly_grant = granted
        user.credit_next_grant_at = None  # 单时钟：续期发放只由 invoice.paid 驱动
    else:
        user.credit_monthly_grant = 0
        user.credit_next_grant_at = None
    user.updated_at = now
