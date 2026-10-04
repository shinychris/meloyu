from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, BaseModel, ISOTimestamp
from .enums import MAX_EXPORTS, PLANS, SUBSCRIPTION_SOURCES, SUBSCRIPTION_STATUSES, _in


class Plan(Base):
    """订阅档位配置（种子配置表，支撑 GET /subscriptions/plans）。

    直接继承 Base（code 单列主键）：若继承 BaseModel 会叠加 id 形成复合主键，
    导致 subscriptions.plan 外键在 SQLite 下失配。
    """

    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint(_in("code", PLANS), name="ck_plans_code"),
        CheckConstraint(_in("max_export", MAX_EXPORTS), name="ck_plans_max_export"),
    )

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(24), nullable=False)
    price_monthly: Mapped[int | None] = mapped_column(Integer)
    price_yearly: Mapped[int | None] = mapped_column(Integer)
    daily_generations: Mapped[int | None] = mapped_column(Integer)
    monthly_credits: Mapped[int | None] = mapped_column(Integer)
    max_export: Mapped[str] = mapped_column(String(4), nullable=False)
    commercial_license: Mapped[bool] = mapped_column(Boolean, nullable=False)
    watermark: Mapped[bool] = mapped_column(Boolean, nullable=False)
    features: Mapped[list] = mapped_column(JSON, nullable=False)
    switchable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    # v0.14.0（P1-8/P1-15）：档位配额。NULL=用代码默认（并发 free1/pro3/studio5；
    # 存储 free 2GB/pro 20GB/studio 100GB/team 200GB）——运营可调表即时生效
    max_concurrent_tasks: Mapped[int | None] = mapped_column(Integer)
    storage_quota_mb: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False)
    updated_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False)

    def __repr__(self) -> str:
        return f"<Plan code={self.code} name={self.name}>"


class Subscription(BaseModel):
    """用户订阅状态与历史；每用户至多一行 status=active（部分唯一索引保证）。"""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(_in("status", SUBSCRIPTION_STATUSES), name="ck_subscriptions_status"),
        CheckConstraint(_in("source", SUBSCRIPTION_SOURCES), name="ck_subscriptions_source"),
        Index("ix_subs_user_status", "user_id", "status"),
        Index(
            "uq_subs_one_active", "user_id", unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    plan: Mapped[str] = mapped_column(
        String(10), ForeignKey("plans.code", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")
    started_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False)
    ended_at: Mapped[str | None] = mapped_column(ISOTimestamp())
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    granted_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # v0.14.0 的 stripe_subscription_id 列随 2026-10-03 Stripe 拆除从模型移除
    # （存量库中的列与历史行保留，迁移条目照常幂等）

    user: Mapped[User] = relationship(back_populates="subscriptions")

    def __repr__(self) -> str:
        return f"<Subscription user={self.user_id} plan={self.plan} status={self.status}>"


class SequenceCounter(Base):
    """人类可读编号发号器（display_code / certificate_code）。单列主键，无 id。"""

    __tablename__ = "sequence_counters"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False)
    updated_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False)

    def __repr__(self) -> str:
        return f"<SequenceCounter key={self.key} value={self.value}>"
