"""内容安全：敏感词检测（生成/歌词/市场等全端口共用的统一入口）。

词库 = 内置 sensitive_words.json + 部署方外置扩展词库（
backend/data/content_policy/extra_words.json，自动合并，无需改代码）。
"""
from __future__ import annotations

import json
from pathlib import Path

_WORDS_PATH = Path(__file__).with_name("sensitive_words.json")


def _load_builtin() -> list[str]:
    with open(_WORDS_PATH, encoding="utf-8") as f:
        return json.load(f)["words"]


def _load_extra_words() -> list[str]:
    """外置扩展词库：backend/data/content_policy/extra_words.json 自动合并。

    部署方按目标市场监管要求放置运营词库（结构 {"words": [...]}），无需改代码；
    文件不存在/格式错误时静默跳过。
    """
    from app.config import settings
    path = settings.data_path / "content_policy" / "extra_words.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [str(w) for w in data.get("words", []) if w]
    except Exception:  # noqa: BLE001
        return []


_BUILTIN = _load_builtin()
SENSITIVE_WORDS: list[str] = _BUILTIN + [
    w for w in _load_extra_words() if w not in _BUILTIN]


def check_sensitive(text: str) -> list[str]:
    """敏感词命中列表（空=通过）。"""
    return [w for w in SENSITIVE_WORDS if w and w in (text or "")]
