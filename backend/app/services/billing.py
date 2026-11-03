"""档位/授权服务（B4：订阅切换 → License 激活口径）。

- license 模式（desktop/enterprise）：档位不可切换——权益由 License 激活决定，
  switch 一律引导去激活入口；list_plans 下发买断价与模式标记。
- cloud 模式（存量过渡）：订阅已停售（Stripe 拆除），付费档切换引导转型公告，
  仅保留降级 free 的本地生效路径。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import LICENSE_PRICE_USD, LICENSE_SALE_PRICE_USD, LICENSE_TRIAL_DAYS, settings
from app.core.errors import err_conflict, err_validation
from app.core.i18n import current_locale, tr
from app.models import Plan, Subscription, User
from app.models.base import utc_now_iso
from app.services import works as works_svc
from app.services.serializers import user_to_dict

# 档位卖点文案（seed 写库为中文，API 层按 locale 展开英文；未收录条目原样返回）
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
    # 2026-10-03：模式与买断价随 plans 一并下发（价格单一事实源；currency 恒 usd）
    return {"plans": plans, "sales_contact": settings.sales_contact_email,
            "currency": "usd",
            "mode": settings.billing_mode,
            "license": {"price_usd": LICENSE_PRICE_USD,
                        "sale_price_usd": LICENSE_SALE_PRICE_USD,
                        "trial_days": LICENSE_TRIAL_DAYS}}


def switch_plan(db: Session, user: User, plan_code: str) -> dict:
    """档位切换（B4 重写）。

    - license 模式（desktop/enterprise）：权益由 License 决定，任何切换 → 409
      引导激活入口；
    - cloud 模式（存量过渡）：订阅停售（Stripe 已拆除），付费档 → 409 转型公告；
      free 降级保留本地生效。
    """
    if plan_code not in ("free", "pro", "studio", "team"):
        raise err_validation(tr("plan 必须为 free/pro/studio/team",
                                "plan must be free/pro/studio/team"))
    if plan_code == "team":
        contact = settings.sales_contact_email
        raise err_validation(
            tr(f"团队/企业版请联系销售{'（' + contact + '）' if contact else ''}",
               f"Please contact sales for the Team plan"
               f"{' (' + contact + ')' if contact else ''}"))
    if settings.billing_mode == "license":
        raise err_conflict(tr(
            "买断制授权：档位不可切换——请在「系统设置 · 授权」输入激活码激活终身授权",
            "One-time license: plans are not switchable — activate your lifetime "
            "license under Settings → License"))
    if plan_code != "free":
        raise err_conflict(tr(
            "订阅已停售：Meloyu 已转型为桌面软件买断制（$399 终身，限时 $129），"
            "付费订阅不再受理",
            "Subscriptions are no longer sold: Meloyu has moved to a one-time "
            "desktop license ($399 lifetime, launch offer $129)"))
    if plan_code == user.plan:
        # 幂等：同档切换仅记录事件
        works_svc.add_event(db, user_id=user.id, action="plan_switch", actor="human",
                            detail={"from": user.plan, "to": plan_code, "granted": 0})
        db.commit()
        db.refresh(user)
        return user_to_dict(user)

    # ---- free 降级（cloud 存量）----
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
