"""参考音频（v0.8.1）：上传 ≤8min 音频作为旋律/风格参考。

合规口径：参考=特征级（BPM/调性/能量/亮度参数化 + 风格描述增强），
**非采样**——生成过程不使用参考音频的任何波形片段；上传者须确认拥有音频权利。
"""
from __future__ import annotations

from sqlalchemy import Boolean, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import BaseModel, ISOTimestamp, new_uuid, utc_now_iso


class ReferenceTrack(BaseModel):
    """参考音轨：原始文件 + 可选浏览器解码 wav + 特征分析结果。"""

    __tablename__ = "reference_tracks"
    __table_args__ = (
        Index("ix_reference_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # 原始上传文件（mp3/wav/m4a 原样保存，供溯源与再次分析）
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    mime: Mapped[str] = mapped_column(String(32), nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_sec: Mapped[float | None] = mapped_column(nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # 上传时「我拥有该音频权利」确认（合规留痕）
    ack_rights: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 特征分析（无可用 wav 时为 None：mp3/m4a 且未随附浏览器解码渲染）
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)

    def __repr__(self) -> str:
        return f"<ReferenceTrack id={self.id} name={self.name!r}>"
