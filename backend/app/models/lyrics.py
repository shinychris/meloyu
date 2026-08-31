from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import BaseModel, ISOTimestamp


class LyricsProject(BaseModel):
    """歌词工程草稿（数据模型设计文档 §D4：V1.1 启用）。

    最小实现为单用户单草稿（uq_lyrics_projects_user 保证），由
    GET/PUT /lyrics/draft 读写 draft_text；title/parsed_structure/rhyme_analysis
    为多工程化预留列，本期不暴露。
    """

    __tablename__ = "lyrics_projects"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_lyrics_projects_user"),
        Index("ix_lyrics_projects_user_updated", "user_id", "updated_at"),
    )

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(50), nullable=False, default="歌词草稿")
    draft_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parsed_structure: Mapped[dict | None] = mapped_column(JSON)  # complete-tags 缓存（预留）
    rhyme_analysis: Mapped[dict | None] = mapped_column(JSON)    # rhyme-check 缓存（预留）
    deleted_at: Mapped[str | None] = mapped_column(ISOTimestamp())

    def __repr__(self) -> str:
        return f"<LyricsProject id={self.id} user={self.user_id} title={self.title}>"
