"""歌词服务：薄适配层（同步、无任务、不扣积分）+ 草稿持久化。

歌词引擎由模型中心全局配置（Ollama 本地模型 / OpenAI 兼容外部 API 二选一）；
未配置时创作型接口（generate/polish）明确报错引导配置——无 AI 兜底通道
（原本地规则引擎已移除，ADR-019）。押韵检查/标签补全是确定性分析工具
（services/lyrics_analysis），与引擎无关、恒可用。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import err_conflict, err_generation_failed, err_sensitive
from app.core.i18n import tr
from app.core.sensitive import check_sensitive
from app.models import LyricsProject, User
from app.models.base import utc_now_iso
from app.providers.llm.base import LLMError
from app.services import lyrics_analysis, model_center


def _provider(db: Session):
    """当前歌词引擎；未配置即业务报错（40901，引导到模型中心配置）。"""
    provider = model_center.get_lyrics_provider(db)
    if provider is None:
        raise err_conflict(tr(
            "歌词引擎未配置：请先在「模型中心 → 歌词引擎」配置 Ollama 或外部 API（OpenAI 兼容）",
            "Lyrics engine not configured: set up Ollama or an external API "
            "(OpenAI-compatible) under Model Center → Lyrics engine first"))
    return provider


def _guard(text: str) -> None:
    if check_sensitive(text):
        raise err_sensitive()
    # 义务②（与 POST /generations 同口径，2026-10-27 补齐）：歌词生成/润色的
    # 输入同样不得冒用 in vivo 艺术家名义/声音
    from app.services.ip_protection import check_ip_protection
    check_ip_protection(text)


def generate(db: Session, theme: str, style_hint: str, mood: str | None, language: str,
             sections: list[str] | None) -> dict:
    _guard(f"{theme} {style_hint or ''} {mood or ''}")
    provider = _provider(db)
    try:
        out = provider.generate(theme=theme, style_hint=style_hint, mood=mood,
                                language=language, sections=sections)
    except LLMError as e:
        raise err_generation_failed(
            tr("歌词生成失败：", "Lyrics generation failed: ") + e.message)
    out.setdefault("engine", provider.engine_name)
    return out


def polish(db: Session, lyrics: str, target_section: str | None, style_hint: str,
           locked_lines: list[int]) -> dict:
    _guard(lyrics)
    provider = _provider(db)
    try:
        out = provider.polish(lyrics=lyrics, target_section=target_section,
                              style_hint=style_hint, locked_lines=locked_lines)
    except LLMError as e:
        raise err_generation_failed(
            tr("歌词润色失败：", "Lyrics polish failed: ") + e.message)
    out.setdefault("engine", provider.engine_name)
    return out


def rhyme_check(db: Session, lyrics: str) -> dict:
    """押韵/重音检查：确定性分析（pypinyin 韵组），与歌词引擎配置无关。"""
    return lyrics_analysis.rhyme_check(lyrics)


def complete_tags(db: Session, lyrics: str) -> dict:
    """结构标签补全：确定性分析，与歌词引擎配置无关。"""
    return lyrics_analysis.complete_tags(lyrics)


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
