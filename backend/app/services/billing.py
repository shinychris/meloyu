"""订阅服务：档位展示 + 切换（MVP 无支付）。"""
from __future__ import annotations

from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import err_validation
from app.models import Plan, Subscription, User
from app.models.base import utc_now_iso
from app.services import credits as credits_svc
from app.services import works as works_svc
from app.services.serializers import user_to_dict


def list_plans(db: Session, user: User) -> dict:
    rows = db.execute(select(Plan).order_by(Plan.sort_order.asc())).scalars().all()
    plans = [{
        "code": p.code, "name": p.name, "price_monthly": p.price_monthly,
        "price_yearly": p.price_yearly, "daily_generations": p.daily_generations,
        "monthly_credits": p.monthly_credits, "max_export": p.max_export,
        "commercial_license": p.commercial_license, "watermark": p.watermark,
        "current": p.code == user.plan, "features": p.features or [],
    } for p in rows]
    return {"plans": plans}


def switch_plan(db: Session, user: User, plan_code: str) -> dict:
    if plan_code == "team":
        raise err_validation("团队版请联系销售")
    if plan_code not in ("free", "pro", "studio"):
        raise err_validation("plan 必须为 free/pro/studio")
    if plan_code == user.plan:
        # 幂等：同档切换仅记录事件
        works_svc.add_event(db, user_id=user.id, action="plan_switch", actor="human",
                            detail={"from": user.plan, "to": plan_code, "granted": 0})
        db.commit()
        db.refresh(user)
        return user_to_dict(user)

    now = utc_now_iso()
    # 关闭旧 active 订阅行
    old_rows = db.execute(select(Subscription).where(
        Subscription.user_id == user.id, Subscription.status == "active")).scalars().all()
    for row in old_rows:
        row.status = "canceled"
        row.ended_at = now
    plan = db.get(Plan, plan_code)
    granted = 0
    if plan and plan.monthly_credits:
        granted = plan.monthly_credits

    sub = Subscription(user_id=user.id, plan=plan_code, status="active", started_at=now,
                       source="switch", granted_credits=granted,
                       created_at=now, updated_at=now)
    db.add(sub)
    db.flush()  # 先落订阅行；grant 内部会 refresh(user)，须在此之前固化 plan 变更
    user.plan = plan_code
    db.flush()

    if granted > 0:
        credits_svc.grant(db, user, granted, "plan_switch", set_carry_over=True)
        user.credit_monthly_grant = granted
        user.credit_next_grant_at = _next_month_first()
    else:
        user.credit_monthly_grant = 0
        user.credit_next_grant_at = None
    user.updated_at = now

    works_svc.add_event(db, user_id=user.id, action="plan_switch", actor="human",
                        detail={"from": old_rows[0].plan if old_rows else user.plan,
                                "to": plan_code, "granted": granted})
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


def _next_month_first() -> str:
    from datetime import datetime
    now = datetime.now(UTC)
    month = now.month + 1
    year = now.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return f"{year:04d}-{month:02d}-01T00:00:00Z"
