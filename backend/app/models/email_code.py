"""邮箱验证码（2026-09-26：内存缓存改落库）。

原进程内存缓存重启即失效、多副本不可用；落库后 TTL 与重发节流由表承载，
注册成功/验证通过即删行。仅存 sha256，不落明文码。
"""
from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel, ISOTimestamp


class EmailCode(BaseModel):
    __tablename__ = "email_codes"
    __table_args__ = (Index("ix_email_codes_email", "email"),)

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    code_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EmailCode {self.email}>"
