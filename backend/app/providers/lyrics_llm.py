"""LLM 歌词 Provider：将歌词创作接入大模型（Ollama 本地 / OpenAI 兼容外部 API）。

- 创作型接口 generate / polish 走 LLM（提示词约束 + JSON 解析 + 行级 diff）；
  通道异常（不可达/超时/坏输出/输出命中敏感词）抛 LLMError 由服务层如实报错，
  不再做无 AI 兜底（原本地规则引擎已移除）。
"""
from __future__ import annotations

import re
from collections.abc import Callable

from app.core.i18n import tr
from app.core.sensitive import check_sensitive
from app.providers.llm.base import LLMError, extract_json
from app.synth.structure import SECTION_TAG, parse_lyrics

ChatFn = Callable[[str, str], str]

_SYSTEM = (
    "你是专业的中文/英文歌词作者，服务于 AI 音乐创作工具。严格遵守："
    "只输出 JSON，不输出任何解释、寒暄或 markdown 之外的内容；"
    "歌词必须有段落标签（如 [Verse]/[Chorus]），每段 2~4 行，每行 6~12 字；"
    "全篇主韵统一（段尾字押韵），意象贴合主题，避免陈词滥调；不使用敏感词汇；"
    "在合适位置用括号表演标记描述演唱方式、情感或配器（中文歌词用中文括号，"
    "如（轻声吟唱）（合唱）（钢琴间奏），每段至多 2 处，标记不单独成段）。"
)

# 段落 → 规范标签（单一事实来源 synth/structure；未收录段退 [Verse]）
_TAG_ZH = dict(SECTION_TAG)


def _structure_of(lyrics: str) -> list[dict]:
    parsed, _ = parse_lyrics(lyrics)
    return [{"section": sec, "line_count": len(lines)} for sec, lines in parsed]


def _content_lines(lyrics: str) -> list[str]:
    parsed, _ = parse_lyrics(lyrics)
    return [ln for _, lines in parsed for ln in lines]


class LLMLyricsProvider:
    """chat 由上层注入（OllamaClient.chat / OpenAICompatClient.chat 的偏函数）。"""

    def __init__(self, chat: ChatFn, engine: str, display_name: str):
        self._chat = chat
        self.engine_name = engine
        self.display_name = display_name

    @property
    def chat(self) -> ChatFn:
        """底层 chat 函数（供生成管线做风格扩写等轻量文本任务复用同一配置）。"""
        return self._chat

    def _ask_json(self, prompt: str) -> dict:
        data = extract_json(self._chat(_SYSTEM, prompt))
        if not isinstance(data, dict):
            raise LLMError("bad_output", tr("模型输出不是 JSON 对象", "Model output is not a JSON object"))
        return data

    # ---- 生成 ----
    def generate(self, theme: str, style_hint: str = "", mood: str | None = None,
                 language: str = "zh", sections: list[str] | None = None) -> dict:
        lang = "英文" if language == "en" else "中文"
        secs = sections or (["verse", "verse", "pre_chorus", "chorus", "chorus"]
                            if language != "en"
                            else ["verse", "pre_chorus", "chorus", "chorus"])
        layout = " → ".join(_TAG_ZH.get(s, "[Verse]") for s in secs[:12])
        prompt = (
            f"根据下面的创作想法写一首完整的{lang}歌词（想法可长可短，"
            f"抓住其中的故事、情绪与画面展开，不要简单复述）。\n"
            f"创作想法：{theme}\n风格提示：{style_hint or '自由发挥'}\n"
            f"情绪：{mood or '未指定'}\n段落结构（按顺序）：{layout}\n"
            f"要求：在段落开头或行内合适位置插入括号表演标记，描述演唱方式、"
            f"情感变化或配器（如（轻声吟唱）（渐强）（钢琴间奏）），全篇 3~6 处。\n\n"
            '输出 JSON：{"lyrics": "带段落标签与括号表演标记的完整歌词", '
            '"alternatives": ["备选版本一（带标签）", "备选版本二（带标签）"]}'
        )
        data = self._ask_json(prompt)
        lyrics = str(data.get("lyrics") or "").strip()
        if len(_content_lines(lyrics)) < 4:
            raise LLMError("bad_output", tr("生成歌词行数不足", "Generated lyrics have too few lines"))
        if check_sensitive(lyrics):
            raise LLMError("bad_output", tr("生成内容命中敏感词", "Generated content hit a sensitive word"))
        alts = data.get("alternatives") or []
        alternatives = []
        for a in alts[:2]:
            text = str(a if isinstance(a, str) else (a or {}).get("lyrics", "")).strip()
            if len(_content_lines(text)) >= 4 and not check_sensitive(text):
                alternatives.append({"lyrics": text})
        return {"lyrics": lyrics, "structure": _structure_of(lyrics),
                "alternatives": alternatives, "engine": self.engine_name}

    # ---- 润色 ----
    def polish(self, lyrics: str, target_section: str | None = None,
               style_hint: str = "", locked_lines: list[int] | None = None) -> dict:
        if check_sensitive(lyrics):
            raise LLMError("bad_output", tr("输入内容命中敏感词", "Input content hit a sensitive word"))
        lock = sorted(set(locked_lines or []))
        prompt = (
            f"润色以下歌词：提升文学性与押韵一致性，保持段落标签与整体结构不变。\n"
            f"保留原词中括号表演标记的用法与位置风格（可按润色后的情绪微调措辞）。\n"
            f"风格提示：{style_hint or '保持原风格'}\n"
            + (f"只润色 {_TAG_ZH.get(target_section, target_section)} 段，其余段落原样保留。\n"
               if target_section else "")
            + (f"第 {lock} 行（按歌词正文行号、不含标签行）为锁定行，必须原样保留。\n"
               if lock else "")
            + f"原歌词：\n{lyrics}\n\n"
            '输出 JSON：{"lyrics": "润色后的完整歌词（含全部段落标签）"}'
        )
        data = self._ask_json(prompt)
        new_lyrics = str(data.get("lyrics") or "").strip()
        old_lines, new_lines = _content_lines(lyrics), _content_lines(new_lyrics)
        if len(new_lines) < 2:
            raise LLMError("bad_output", tr("润色结果行数不足", "Polished lyrics have too few lines"))
        if check_sensitive(new_lyrics):
            raise LLMError("bad_output", tr("润色内容命中敏感词", "Polished content hit a sensitive word"))
        changes: list[dict] = []
        polished_sections: list[str] = []
        if len(old_lines) == len(new_lines):  # 行对齐才给出可信 diff
            for i, (before, after) in enumerate(zip(old_lines, new_lines, strict=True), start=1):
                if before != after and i not in lock:
                    changes.append({"line_no": i, "before": before, "after": after})
            old_parsed, _ = parse_lyrics(lyrics)
            new_parsed, _ = parse_lyrics(new_lyrics)
            if len(old_parsed) == len(new_parsed):
                idx = 0
                for (sec, ols), (_, nls) in zip(old_parsed, new_parsed, strict=True):
                    chunk_o = old_lines[idx:idx + len(ols)]
                    chunk_n = new_lines[idx:idx + len(nls)]
                    idx += len(ols)
                    if chunk_o != chunk_n:
                        polished_sections.append(sec)
        return {"lyrics": new_lyrics, "changes": changes,
                "polished_sections": polished_sections, "engine": self.engine_name}


_MODEL_TAG_RE = re.compile(r"^[A-Za-z0-9._:@/+-]{1,100}$")


def valid_model_tag(tag: str) -> bool:
    return bool(_MODEL_TAG_RE.match((tag or "").strip()))
