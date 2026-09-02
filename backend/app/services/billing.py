"""订阅服务：档位展示 + 切换（v0.7.0：付费档经 Stripe 激活，本服务仅处理降级）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import err_conflict, err_validation
from app.core.i18n import current_locale, tr
from app.models import Plan, Subscription, User
from app.models.base import utc_now_iso
from app.services import works as works_svc
from app.services.serializers import user_to_dict

# 档位卖点文案（seed 写库为中文，API 层按 locale 展开英文；未收录条目原样返回）
# v0.7.0：免费档卖点口径修正——实际能力为「SHA-256 指纹登记」（频域水印未实现，
# 不再宣称水印，见盘点报告 R-44）
_FEATURE_EN = {
    "每日 5 次生成": "5 generations per day",
    "仅 MP3 导出": "MP3 export only",
    "非商用 · 指纹登记": "Non-commercial · fingerprint-registered",
    "商用授权 + 证书": "Commercial license + certificate",
    "WAV 48k/24bit · MIDI · 4 Stems": "WAV 48k/24bit · MIDI · 4 stems",
    "每月 2,500 积分可结转": "2,500 credits per month, rollable",
    "全部 Pro 权益 + 12 Stems（V1.1）": "All Pro benefits + 12 stems (V1.1)",
    "专业修调/AI 编曲建议（V2）": "Pro tuning / AI arrangement advice (V2)",
    "每月 10,000 积分 · 优先队列": "10,000 credits per month · priority queue",
    "团队空间与协作（V1.1）": "Team workspace & collaboration (V1.1)",
    "API 按量计费": "Usage-based API billing",
    "专属合规支持": "Dedicated compliance support",
}


def _feature_label(feature: str) -> str:
    if current_locale() == "zh":
        return feature
    return _FEATURE_EN.get(feature, feature)


def _is_credit_feature(feature: str) -> bool:
    """积分类卖点（monthly_credits 字段已单独返回，features 列表不再重复展示；
    判定不依赖单一措辞：中文「积分」或英文 credit 关键词，zh/en 均命中）。"""
    low = feature.lower()
    return "积分" in feature or "credit" in low


def list_plans(db: Session, user: User) -> dict:
    rows = db.execute(select(Plan).order_by(Plan.sort_order.asc())).scalars().all()
    plans = [{
        "code": p.code, "name": p.name, "price_monthly": p.price_monthly,
        "price_yearly": p.price_yearly, "daily_generations": p.daily_generations,
        "monthly_credits": p.monthly_credits, "max_export": p.max_export,
        "commercial_license": p.commercial_license, "watermark": p.watermark,
        "current": p.code == user.plan,
        "features": [_feature_label(f) for f in (p.features or [])
                     if not _is_credit_feature(_feature_label(f))],
    } for p in rows]
    return {"plans": plans}


def switch_plan(db: Session, user: User, plan_code: str) -> dict:
    """档位切换（v0.7.0 商业化口径）：

    - free：允许（降级/维持，不涉及资金）；
    - pro/studio：**不再直接生效**（P0-4）——必须经 Stripe 支付，前端跳
      POST /billing/checkout 完成订阅，webhook 确认后由 _activate_plan 激活；
      Stripe 未配置时付费档整体不可用；
    - team：联系销售。
    """
    if plan_code == "team":
        raise err_validation(tr("团队版请联系销售", "Please contact sales for the Team plan"))
    if plan_code not in ("free", "pro", "studio"):
        raise err_validation(tr("plan 必须为 free/pro/studio", "plan must be free/pro/studio"))
    if plan_code == user.plan:
        # 幂等：同档切换仅记录事件
        works_svc.add_event(db, user_id=user.id, action="plan_switch", actor="human",
                            detail={"from": user.plan, "to": plan_code, "granted": 0})
        db.commit()
        db.refresh(user)
        return user_to_dict(user)
    if plan_code != "free":
        from app.services import stripe_billing
        if not stripe_billing.stripe_enabled():
            raise err_conflict(tr(
                "付费档需经 Stripe 支付，但支付未配置（STRIPE_SECRET_KEY），请联系管理员",
                "Paid plans require Stripe payment, which is not configured "
                "(STRIPE_SECRET_KEY); please contact the administrator"))
        raise err_conflict(tr(
            "付费档需经 Stripe 订阅支付：请通过定价页发起订阅，支付完成后自动生效",
            "Paid plans require a Stripe subscription: subscribe from the pricing page; "
            "the plan activates automatically after payment"))

    # ---- free 降级 ----
    now = utc_now_iso()
    old_rows = db.execute(select(Subscription).where(
        Subscription.user_id == user.id, Subscription.status == "active")).scalars().all()
    for row in old_rows:
        row.status = "canceled"
        row.ended_at = now
    user.plan = "free"
    user.credit_monthly_grant = 0
    user.credit_next_grant_at = None
    user.updated_at = now
    db.add(Subscription(user_id=user.id, plan="free", status="active", started_at=now,
                        source="switch", granted_credits=0, created_at=now, updated_at=now))
    works_svc.add_event(db, user_id=user.id, action="plan_switch", actor="human",
                        detail={"from": (old_rows[0].plan if old_rows else user.plan),
                                "to": "free", "granted": 0})
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


def _next_month_first() -> str:
    from datetime import UTC, datetime
    now = datetime.now(UTC)
    month = now.month + 1
    year = now.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return f"{year:04d}-{month:02d}-01T00:00:00Z"
