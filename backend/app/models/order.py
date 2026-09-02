"""支付订单（P1-1，D-2 决策：Stripe）。

- kind ∈ subscription（订阅 pro/studio，月/年）| topup（积分充值包）
- status ∈ pending（Checkout 已创建未支付）| paid（webhook 确认）| failed | refunded
- Stripe 幂等：checkout session id 唯一索引（webhook 重放安全网）
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel, ISOTimestamp
from .enums import ORDER_KINDS, ORDER_STATUSES, _in


class Order(BaseModel):
    """Stripe 支付订单留痕（账务对账与 webhook 幂等依据）。"""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(_in("kind", ORDER_KINDS), name="ck_orders_kind"),
        CheckConstraint(_in("status", ORDER_STATUSES), name="ck_orders_status"),
        Index("ix_orders_user_created", "user_id", "created_at"),
        Index("uq_orders_checkout", "stripe_checkout_id", unique=True),
    )

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # subscription：plan ∈ pro|studio + interval ∈ monthly|yearly；topup：credits 数
    plan: Mapped[str | None] = mapped_column(String(10))
    interval: Mapped[str | None] = mapped_column(String(8))
    credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    amount_usd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 美分
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="usd")
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    stripe_checkout_id: Mapped[str | None] = mapped_column(String(120))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(120))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(120))
    # webhook 事件去重（Stripe 可能重放 checkout.session.completed 等）
    stripe_event_id: Mapped[str | None] = mapped_column(String(120))
    paid_at: Mapped[ISOTimestamp | None] = mapped_column(ISOTimestamp())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Order user={self.user_id} {self.kind} {self.status}>"
