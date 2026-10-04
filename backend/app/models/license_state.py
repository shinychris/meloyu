"""License 激活态与试用状态（desktop/enterprise 形态，单行表 id=1）。

2026-10-03 定位转型（D-1/D-2）：买断制终身授权 + 14 天全功能试用。
- trial_started_at：首次启动落库（试用起点，D-2：无免费层）
- license_key/payload/activated_at：激活后写入（Ed25519 离线验签）
- device_id：本机设备指纹（在线激活治理用；离线使用不受影响）
"""
from __future__ import annotations

import uuid

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, ISOTimestamp, utc_now_iso

STATE_ID = 1


class LicenseState(Base):
    __tablename__ = "license_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=STATE_ID)
    trial_started_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                                  default=utc_now_iso)
    device_id: Mapped[str] = mapped_column(String(32), nullable=False,
                                           default=lambda: uuid.uuid4().hex)
    license_key: Mapped[str | None] = mapped_column(Text)
    license_payload: Mapped[dict | None] = mapped_column(JSON)
    activated_at: Mapped[str | None] = mapped_column(ISOTimestamp())
    updated_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso, onupdate=utc_now_iso)
