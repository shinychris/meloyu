from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModel, ISOTimestamp
from .enums import CREDIT_REASONS, PLANS, _in


class User(BaseModel):
    """用户账户（/auth/*、/credits/balance 数据源）。"""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_in("plan", PLANS), name="ck_users_plan"),
        CheckConstraint("credit_balance >= 0", name="ck_users_balance_nonneg"),
    )

    _dict_exclude = frozenset({"password_hash"})

    email: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(60), nullable=False)  # bcrypt cost=12
    nickname: Mapped[str] = mapped_column(String(24), nullable=False)
    plan: Mapped[str] = mapped_column(
        String(10), ForeignKey("plans.code", ondelete="RESTRICT"),
        nullable=False, default="free",
    )
    credit_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit_monthly_grant: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit_carried_over: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit_next_grant_at: Mapped[str | None] = mapped_column(ISOTimestamp())

    works: Mapped[list[Work]] = relationship(back_populates="user")
    tasks: Mapped[list[Task]] = relationship(back_populates="user")
    transactions: Mapped[list[CreditTransaction]] = relationship(back_populates="user")
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} plan={self.plan}>"


class CreditTransaction(BaseModel):
    """积分流水（不可变账本：只 INSERT，禁止 UPDATE/DELETE）。"""

    __tablename__ = "credit_transactions"
    __table_args__ = (
        CheckConstraint("delta <> 0", name="ck_ct_delta_nonzero"),
        CheckConstraint(_in("reason", CREDIT_REASONS), name="ck_ct_reason"),
        CheckConstraint("balance_after >= 0", name="ck_ct_balance_nonneg"),
        Index("ix_ct_user_created", "user_id", "created_at"),
        Index("ix_ct_task", "ref_task_id"),
    )

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_task_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("tasks.id", ondelete="SET NULL")
    )
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped[User] = relationship(back_populates="transactions")

    def __repr__(self) -> str:
        return (
            f"<CreditTransaction user={self.user_id} delta={self.delta} "
            f"reason={self.reason} balance_after={self.balance_after}>"
        )
