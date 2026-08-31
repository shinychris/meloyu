"""歌词服务：薄适配层，调 providers.lyrics（同步、无任务、不扣积分）+ 草稿持久化。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import err_sensitive
from app.models import LyricsProject, User
from app.models.base import utc_now_iso
from app.providers.lyrics_local import LocalLyricsProvider, check_sensitive

_provider = LocalLyricsProvider()


def _guard(text: str) -> None:
    if check_sensitive(text):
        raise err_sensitive()


def generate(theme: str, style_hint: str, mood: str | None, language: str,
             sections: list[str] | None) -> dict:
    _guard(f"{theme} {style_hint or ''} {mood or ''}")
    return _provider.generate(theme=theme, style_hint=style_hint, mood=mood,
                              language=language, sections=sections)


def polish(lyrics: str, target_section: str | None, style_hint: str,
           locked_lines: list[int]) -> dict:
    _guard(lyrics)
    return _provider.polish(lyrics=lyrics, target_section=target_section,
                            style_hint=style_hint, locked_lines=locked_lines)


def rhyme_check(lyrics: str) -> dict:
    return _provider.rhyme_check(lyrics)


def complete_tags(lyrics: str) -> dict:
    return _provider.complete_tags(lyrics)


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
        row = LyricsProject(user_id=user.id, title="歌词草稿", draft_text=text,
                            created_at=now, updated_at=now)
        db.add(row)
    else:
        row.draft_text = text
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return {"text": row.draft_text, "updated_at": row.updated_at}
