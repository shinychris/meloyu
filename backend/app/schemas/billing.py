"""billing 请求模型（P1-1，v0.7.0）。"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.core.i18n import tr


class CheckoutRequest(BaseModel):
    """创建 Stripe Checkout Session：订阅（plan+interval）或积分充值包（topup）。"""
    kind: str
    plan: str | None = Field(default=None, max_length=10)
    interval: str | None = Field(default=None, max_length=8)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in ("subscription", "topup"):
            raise ValueError(tr("kind 必须为 subscription/topup",
                                "kind must be subscription/topup"))
        return v

    @field_validator("plan")
    @classmethod
    def _plan(cls, v: str | None) -> str | None:
        if v is not None and v not in ("pro", "studio"):
            raise ValueError(tr("plan 必须为 pro/studio", "plan must be pro/studio"))
        return v

    @field_validator("interval")
    @classmethod
    def _interval(cls, v: str | None) -> str | None:
        if v is not None and v not in ("monthly", "yearly"):
            raise ValueError(tr("interval 必须为 monthly/yearly",
                                "interval must be monthly/yearly"))
        return v
