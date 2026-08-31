from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import BaseModel, ISOTimestamp
from .enums import (
    CANDIDATE_LABELS,
    EVENT_ACTIONS,
    EVENT_ACTORS,
    KEY_MODES,
    LANGUAGES,
    MODELS,
    TIME_SIGNATURES,
    TONICS,
    VERSION_SOURCES,
    VOCALS,
    WORK_STATUSES,
    _in,
)


class Work(BaseModel):
    """作品（契约资源名 work）。bpm/key/duration/model/preview 为采用候选时回写的快照。"""

    __tablename__ = "works"
    __table_args__ = (
        CheckConstraint(_in("status", WORK_STATUSES), name="ck_works_status"),
        CheckConstraint(_in("model", MODELS), name="ck_works_model"),
        CheckConstraint(_in("key_tonic", TONICS), name="ck_works_key_tonic"),
        CheckConstraint(_in("key_mode", KEY_MODES), name="ck_works_key_mode"),
        CheckConstraint("bpm BETWEEN 60 AND 174", name="ck_works_bpm"),
        CheckConstraint("duration_sec BETWEEN 30 AND 240", name="ck_works_duration"),
        Index("ix_works_user_status_updated", "user_id", "status", "updated_at"),
        Index("ix_works_status_trashed", "status", "trashed_at"),
        Index("ix_works_user_favorite", "user_id", "favorite"),
    )

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    display_code: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="active")
    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    bpm: Mapped[int] = mapped_column(Integer, nullable=False)
    key_tonic: Mapped[str] = mapped_column(String(2), nullable=False)
    key_mode: Mapped[str] = mapped_column(String(8), nullable=False)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(8), nullable=False)
    cover_color: Mapped[str | None] = mapped_column(String(7))
    version_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("versions.id", ondelete="SET NULL", use_alter=True,
                   name="fk_works_active_version")
    )
    preview_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL", use_alter=True,
                   name="fk_works_preview_file")
    )
    trashed_at: Mapped[str | None] = mapped_column(ISOTimestamp())

    user: Mapped[User] = relationship(back_populates="works")
    versions: Mapped[list[Version]] = relationship(
        back_populates="work",
        foreign_keys="Version.work_id",
        cascade="save-update, merge",
    )
    active_version: Mapped[Version | None] = relationship(
        foreign_keys=[active_version_id], post_update=True
    )
    preview_file: Mapped[File | None] = relationship(
        foreign_keys=[preview_file_id], post_update=True
    )
    events: Mapped[list[EditEvent]] = relationship(back_populates="work")

    def __repr__(self) -> str:
        return f"<Work id={self.id} display_code={self.display_code} title={self.title}>"


class Version(BaseModel):
    """版本树节点。params 为契约 §1.6 version.params 完整快照。"""

    __tablename__ = "versions"
    __table_args__ = (
        CheckConstraint(_in("source", VERSION_SOURCES), name="ck_versions_source"),
        Index("ix_versions_work_created", "work_id", "created_at"),
        Index("ix_versions_parent", "parent_version_id"),
    )

    work_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("works.id", ondelete="CASCADE"), nullable=False
    )
    parent_version_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("versions.id", ondelete="CASCADE")
    )
    version_no: Mapped[str] = mapped_column(String(8), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="generate")
    active_candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL", use_alter=True,
                   name="fk_versions_active_candidate")
    )
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    params: Mapped[dict] = mapped_column(JSON, nullable=False)
    lyrics: Mapped[str] = mapped_column(Text, nullable=False, default="")
    inferred_structure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    work: Mapped[Work] = relationship(back_populates="versions", foreign_keys=[work_id])
    parent_version: Mapped[Version | None] = relationship(
        "Version", remote_side="Version.id", foreign_keys=[parent_version_id]
    )
    candidates: Mapped[list[Candidate]] = relationship(
        back_populates="version", foreign_keys="Candidate.version_id"
    )
    active_candidate: Mapped[Candidate | None] = relationship(
        foreign_keys=[active_candidate_id], post_update=True
    )
    files: Mapped[list[File]] = relationship(back_populates="version")
    events: Mapped[list[EditEvent]] = relationship(back_populates="version")

    def __repr__(self) -> str:
        return f"<Version id={self.id} work={self.work_id} version_no={self.version_no}>"


class Candidate(BaseModel):
    """生成候选（label A/B，MVP 每版本 2 条）。"""

    __tablename__ = "candidates"
    __table_args__ = (
        CheckConstraint(_in("label", CANDIDATE_LABELS), name="ck_candidates_label"),
        CheckConstraint("seed BETWEEN 0 AND 4294967295", name="ck_candidates_seed"),
        CheckConstraint("quality_score BETWEEN 0 AND 100", name="ck_candidates_score"),
        CheckConstraint("bpm BETWEEN 60 AND 174", name="ck_candidates_bpm"),
        CheckConstraint(_in("key_tonic", TONICS), name="ck_candidates_key_tonic"),
        CheckConstraint(_in("key_mode", KEY_MODES), name="ck_candidates_key_mode"),
        CheckConstraint(_in("time_signature", TIME_SIGNATURES), name="ck_candidates_time_signature"),
        CheckConstraint(_in("vocal", VOCALS), name="ck_candidates_vocal"),
        CheckConstraint(_in("language", LANGUAGES), name="ck_candidates_language"),
        UniqueConstraint("version_id", "label", name="uq_candidates_version_label"),
    )

    version_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("versions.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(2), nullable=False)
    adopted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    # V1.3 起允许空：外部模型候选不产出 AI 质量分（不造假分）；本地引擎候选保留确定性启发分
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    bpm: Mapped[int] = mapped_column(Integer, nullable=False)
    key_tonic: Mapped[str] = mapped_column(String(2), nullable=False)
    key_mode: Mapped[str] = mapped_column(String(8), nullable=False)
    time_signature: Mapped[str] = mapped_column(String(4), nullable=False)
    vocal: Mapped[str] = mapped_column(String(16), nullable=False)
    language: Mapped[str] = mapped_column(String(3), nullable=False)
    style_tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    structure: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    applied_negative: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    version: Mapped[Version] = relationship(
        back_populates="candidates", foreign_keys=[version_id]
    )
    files: Mapped[list[File]] = relationship(back_populates="candidate")

    def __repr__(self) -> str:
        return (
            f"<Candidate id={self.id} version={self.version_id} label={self.label} "
            f"score={self.quality_score}>"
        )


class EditEvent(BaseModel):
    """操作留痕（不可变，只 INSERT；work_id/version_id 可空见 D7）。"""

    __tablename__ = "edit_events"
    __table_args__ = (
        CheckConstraint(_in("action", EVENT_ACTIONS), name="ck_events_action"),
        CheckConstraint(_in("actor", EVENT_ACTORS), name="ck_events_actor"),
        Index("ix_events_work_created", "work_id", "created_at"),
        Index("ix_events_version", "version_id"),
    )

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    work_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("works.id", ondelete="CASCADE")
    )
    version_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("versions.id", ondelete="CASCADE")
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(8), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    work: Mapped[Work | None] = relationship(back_populates="events")
    version: Mapped[Version | None] = relationship(back_populates="events")

    def __repr__(self) -> str:
        return f"<EditEvent id={self.id} work={self.work_id} action={self.action} actor={self.actor}>"
