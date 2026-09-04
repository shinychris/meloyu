"""我的口味画像（V2-b，v0.9.1）：从用户作品库统计生成偏好，一键预填参数。

口径（PRD §4.3「风格定制模型 My Taste」的本产品落地）：画像=作品库参数统计
（BPM 中位数/调性众数/器乐密度均值/人声与语言偏好/风格标签 top-N），生成时由
前端一键预填（建议语义，用户可改）；不做隐式服务端改写，不训练任何模型。
"""
from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel, ISOTimestamp, utc_now_iso


class TasteProfile(BaseModel):
    """用户口味画像（每用户一行，rebuild 幂等覆盖）。"""

    __tablename__ = "taste_profiles"

    user_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    profile: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sample_count: Mapped[int] = mapped_column(nullable=False, default=0)
    updated_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)

    def __repr__(self) -> str:
        return f"<TasteProfile user={self.user_id} n={self.sample_count}>"
