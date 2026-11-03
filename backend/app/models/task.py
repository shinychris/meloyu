from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import BaseModel, ISOTimestamp
from .enums import (
    EXPORT_FORMATS,
    FILE_KINDS,
    STAGE_KEYS,
    STEM_NAMES,
    TASK_STATUSES,
    TASK_TYPES,
    _in,
)


class Task(BaseModel):
    """异步任务（generation / export 统一状态机）。"""

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(_in("type", TASK_TYPES), name="ck_tasks_type"),
        CheckConstraint(_in("status", TASK_STATUSES), name="ck_tasks_status"),
        CheckConstraint(_in("stage_key", STAGE_KEYS), name="ck_tasks_stage_key"),
        CheckConstraint(_in("format", EXPORT_FORMATS), name="ck_tasks_format"),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_tasks_progress"),
        Index("ix_tasks_user_created", "user_id", "created_at"),
        Index("ix_tasks_user_type_status", "user_id", "type", "status"),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_work", "work_id"),
    )

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage_key: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    # 运行期阶段文案含通道细节（实测最长 90 字符）：原 String(32) 在 PG 拒写
    stage_label: Mapped[str] = mapped_column(String(120), nullable=False, default="排队中")
    error_code: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    work_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("works.id", ondelete="SET NULL")
    )
    version_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("versions.id", ondelete="SET NULL")
    )
    format: Mapped[str | None] = mapped_column(String(10))  # release=7字符
    provider: Mapped[str | None] = mapped_column(String(16))
    # 歌词引擎快照（auto_lyrics / simple 扩写实际通道，用量统计维度）
    lyrics_engine: Mapped[str | None] = mapped_column(String(16))
    # derive_seed 产 0~4294967295（无符号 32 位）：PG Integer 为有符号
    # 32 位，半数取值溢出（SQLite 动态类型无感）——v0.15.0 切 PG 改 BigInteger
    seed: Mapped[int | None] = mapped_column(BigInteger)
    cost_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_payload: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[str | None] = mapped_column(ISOTimestamp())
    finished_at: Mapped[str | None] = mapped_column(ISOTimestamp())

    user: Mapped[User] = relationship(back_populates="tasks")

    def __repr__(self) -> str:
        return f"<Task id={self.id} type={self.type} status={self.status} progress={self.progress}>"


class File(BaseModel):
    """文件资产注册表：音频/MIDI/证书的唯一合法流式入口。"""

    __tablename__ = "files"
    __table_args__ = (
        CheckConstraint(_in("kind", FILE_KINDS), name="ck_files_kind"),
        CheckConstraint(_in("stem_name", STEM_NAMES), name="ck_files_stem_name"),
        CheckConstraint("bytes > 0", name="ck_files_bytes"),
        Index("ix_files_version_kind", "version_id", "kind"),
        Index("ix_files_candidate", "candidate_id"),
        Index("ix_files_work", "work_id"),
    )

    work_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("works.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("versions.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("candidates.id", ondelete="CASCADE")
    )
    # export_release_zip=18 字符：原 String(16) 在 PG 拒写（发行导出必炸），
    # SQLite 不校验长度无感——v0.15.0 放宽
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    stem_name: Mapped[str | None] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    mime: Mapped[str] = mapped_column(String(32), nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_sec: Mapped[float | None] = mapped_column(Float)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    version: Mapped[Version] = relationship(back_populates="files")
    candidate: Mapped[Candidate | None] = relationship(back_populates="files")

    def __repr__(self) -> str:
        return f"<File id={self.id} kind={self.kind} name={self.name}>"
