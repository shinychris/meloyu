from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import BaseModel, ISOTimestamp
from .enums import LICENSE_TYPES, _in


class Certificate(BaseModel):
    """授权证书签发记录：每次 GET /versions/{id}/certificate 下载 = 一次签发 INSERT。"""

    __tablename__ = "certificates"
    __table_args__ = (
        CheckConstraint(_in("license_type", LICENSE_TYPES), name="ck_certificates_license_type"),
        Index("ix_certificates_version", "version_id"),
    )

    certificate_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    work_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("works.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("versions.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_display: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(8), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False)
    license_type: Mapped[str] = mapped_column(String(16), nullable=False)
    plan_at_issuance: Mapped[str] = mapped_column(String(10), nullable=False)
    license_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    edit_events_count: Mapped[int] = mapped_column(Integer, nullable=False)
    human_summary: Mapped[list] = mapped_column(JSON, nullable=False)
    master_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    preview_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    disclosure: Mapped[str] = mapped_column(Text, nullable=False)
    issued_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False)
    file_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("files.id", ondelete="SET NULL")
    )

    def __repr__(self) -> str:
        return f"<Certificate code={self.certificate_code} version={self.version_id}>"
