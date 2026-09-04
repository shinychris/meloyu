"""API 密钥表（FR-19，v0.8.2）。"""
from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel, ISOTimestamp, new_uuid, utc_now_iso


class ApiKey(BaseModel):
    """开放 API 密钥：落库只存 sha256；吊销=revoked_at 置位（行保留审计）。"""

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_user", "user_id"),
        Index("uq_api_keys_hash", "key_hash", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    last_used_at: Mapped[str | None] = mapped_column(ISOTimestamp())
    revoked_at: Mapped[str | None] = mapped_column(ISOTimestamp())
    created_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)

    def __repr__(self) -> str:
        return f"<ApiKey id={self.id} prefix={self.prefix}>"
