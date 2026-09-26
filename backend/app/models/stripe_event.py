"""Stripe webhook 事件去重表（P0-2，2026-09-26 商业化审查）。

持久化幂等：处理**成功**的事件在同事务写入本表；事件重放/进程重启后查表去重。
处理抛异常时绝不落表（调用方回滚并 5xx），Stripe 重试直至成功——修复原
实现两处资金级缺陷：①去重只剩进程内 set（重启失忆，重放重发积分）；
②异常仍标记已处理（用户付款后积分永久丢失）。
"""
from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, ISOTimestamp


class StripeEvent(Base):
    event_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False)

    __tablename__ = "stripe_events"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StripeEvent {self.type} {self.event_id}>"
