"""团队空间与协作评论（v0.8.3）。

角色：owner（所有者）/ editor（编辑）/ commenter（评论）/ viewer（查看），
按 rank 判权（owner 4 > editor 3 > commenter 2 > viewer 1）：
- viewer：作品/版本/候选/文件读取
- commenter：+ 时间轴锚定评论
- editor：+ 采用/导出/派生/信息编辑等写操作
- owner：+ 成员管理/共享管理/删除作品
评论锚定：time_sec 绑定作品时间轴（0~duration），前端跳转播放定位。
"""
from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel, ISOTimestamp, new_uuid, utc_now_iso

TEAM_ROLES = ("owner", "editor", "commenter", "viewer")
ROLE_RANK = {"owner": 4, "editor": 3, "commenter": 2, "viewer": 1}


class TeamSpace(BaseModel):
    """团队空间：所有者建圈，作品可共享进来（work.space_id）。"""

    __tablename__ = "team_spaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)

    def __repr__(self) -> str:
        return f"<TeamSpace id={self.id} name={self.name!r}>"


class TeamMember(BaseModel):
    """空间成员（角色制；owner 行随空间创建写入，不可降级/移除）。"""

    __tablename__ = "team_members"
    __table_args__ = (
        CheckConstraint("role IN ('owner','editor','commenter','viewer')",
                        name="ck_team_members_role"),
        UniqueConstraint("space_id", "user_id", name="uq_team_member"),
        Index("ix_team_members_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    space_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("team_spaces.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False, default="viewer")
    invited_by: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)

    def __repr__(self) -> str:
        return f"<TeamMember space={self.space_id} user={self.user_id} role={self.role}>"


class WorkComment(BaseModel):
    """协作评论：锚定作品时间轴 time_sec（验收口径）。"""

    __tablename__ = "work_comments"
    __table_args__ = (
        CheckConstraint("time_sec >= 0", name="ck_comments_time"),
        Index("ix_comments_work_created", "work_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    work_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("works.id", ondelete="CASCADE"), nullable=False)
    version_id: Mapped[str | None] = mapped_column(String(32))
    author_id: Mapped[str] = mapped_column(String(32), nullable=False)
    author_nickname: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    time_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)

    def __repr__(self) -> str:
        return f"<WorkComment work={self.work_id} t={self.time_sec}>"
