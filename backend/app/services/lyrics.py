"""歌词服务：薄适配层，调 providers.lyrics（同步、无任务、不扣积分）。"""
from __future__ import annotations

from app.core.errors import err_sensitive
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
