"""歌词服务：薄适配层，调歌词 provider（同步、无任务、不扣积分）+ 草稿持久化。

V1.2：provider 由模型中心全局配置动态决定（本地规则 / Ollama 本地模型 /
OpenAI 兼容外部 API）；LLM 通道失败时 provider 内部自动回退本地规则引擎，
响应带 engine / fallback 字段。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import err_sensitive
from app.models import LyricsProject, User
from app.models.base import utc_now_iso
from app.providers.lyrics_local import check_sensitive
from app.services.model_center import get_lyrics_provider
from app.core.i18n import tr


def _guard(text: str) -> None:
    if check_sensitive(text):
        raise err_sensitive()


def generate(db: Session, theme: str, style_hint: str, mood: str | None, language: str,
             sections: list[str] | None) -> dict:
    _guard(f"{theme} {style_hint or ''} {mood or ''}")
    provider = get_lyrics_provider(db)
    out = provider.generate(theme=theme, style_hint=style_hint, mood=mood,
                            language=language, sections=sections)
    out.setdefault("engine", provider.engine_name)
    out.setdefault("fallback", False)
    return out


def polish(db: Session, lyrics: str, target_section: str | None, style_hint: str,
           locked_lines: list[int]) -> dict:
    _guard(lyrics)
    provider = get_lyrics_provider(db)
    out = provider.polish(lyrics=lyrics, target_section=target_section,
                          style_hint=style_hint, locked_lines=locked_lines)
    out.setdefault("engine", provider.engine_name)
    out.setdefault("fallback", False)
    return out


def rhyme_check(db: Session, lyrics: str) -> dict:
    provider = get_lyrics_provider(db)
    out = provider.rhyme_check(lyrics)
    out.setdefault("engine", "localsynth-lyrics")  # 计算型接口恒为本地规则
    out.setdefault("fallback", False)
    return out


def complete_tags(db: Session, lyrics: str) -> dict:
    provider = get_lyrics_provider(db)
    out = provider.complete_tags(lyrics)
    out.setdefault("engine", "localsynth-lyrics")  # 计算型接口恒为本地规则
    out.setdefault("fallback", False)
    return out


# ---------- V1.1 草稿云端持久化（单用户单草稿） ----------

def _draft_row(db: Session, user: User) -> LyricsProject | None:
    return db.execute(select(LyricsProject).where(
        LyricsProject.user_id == user.id,
        LyricsProject.deleted_at.is_(None))).scalars().first()


def get_draft(db: Session, user: User) -> dict:
    row = _draft_row(db, user)
    if row is None:
        return {"text": "", "updated_at": None}
    return {"text": row.draft_text, "updated_at": row.updated_at}


def save_draft(db: Session, user: User, text: str) -> dict:
    """upsert 单草稿。不做敏感词拦截：草稿属用户私有编辑态，
    敏感词在生成提交（POST /generations）与歌词助手段统一拦截。"""
    row = _draft_row(db, user)
    now = utc_now_iso()
    if row is None:
        row = LyricsProject(user_id=user.id, title=tr("歌词草稿", "Lyrics draft"), draft_text=text,
                            created_at=now, updated_at=now)
        db.add(row)
    else:
        row.draft_text = text
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return {"text": row.draft_text, "updated_at": row.updated_at}
