"""LocalLyricsProvider：中文规则引擎（数据驱动词库 + pypinyin 韵组，架构 §8.3）。

同步、无状态、不扣积分；同输入同输出（seeded random.Random，非音频路径）。
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

from pypinyin import Style, pinyin

from app.core.i18n import tr
from app.synth.structure import SECTION_ALIASES, TAG_RE, parse_lyrics

BANKS_DIR = Path(__file__).parent / "lyrics" / "banks"


def _load(name: str) -> dict:
    with open(BANKS_DIR / name, encoding="utf-8") as f:
        return json.load(f)


_IMAGERY = _load("imagery.json")
_RHYMES = _load("rhymes.json")
_TEMPLATES = _load("templates.json")
SENSITIVE_WORDS: list[str] = _load("sensitive_words.json")["words"]


def _load_extra_words() -> list[str]:
    """外置扩展词库（P1-4）：backend/data/content_policy/extra_words.json 自动合并。

    部署方按目标市场监管要求放置运营词库（结构 {"words": [...]}），无需改代码；
    文件不存在/格式错误时静默跳过。
    """
    import json as _json

    from app.config import settings
    path = settings.data_path / "content_policy" / "extra_words.json"
    if not path.exists():
        return []
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
        return [str(w) for w in data.get("words", []) if w]
    except Exception:  # noqa: BLE001
        return []


SENSITIVE_WORDS = SENSITIVE_WORDS + [
    w for w in _load_extra_words() if w not in SENSITIVE_WORDS]

# final → 13 辙
_FINAL_TO_GROUP: dict[str, str] = {}
for group, finals in _RHYMES["groups"].items():
    for f in finals:
        _FINAL_TO_GROUP[f] = group


def check_sensitive(text: str) -> list[str]:
    """敏感词命中列表（空=通过）。"""
    return [w for w in SENSITIVE_WORDS if w and w in (text or "")]


def final_of(char: str) -> str:
    if not char.strip():
        return ""
    py = pinyin(char, style=Style.FINALS, strict=False)
    return (py[0][0] or "") if py and py[0] else ""


def pinyin_of(char: str) -> str:
    py = pinyin(char, style=Style.NORMAL)
    return (py[0][0] or "") if py and py[0] else ""


def rhyme_group_of(final: str) -> str | None:
    """final → 13 辙组名（如 ai → 怀来）。"""
    f = final.replace("ü", "v").replace("û", "v")
    return _FINAL_TO_GROUP.get(f)


def _rng_for(*parts) -> random.Random:
    seed_hex = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return random.Random(int(seed_hex[:16], 16))


class LocalLyricsProvider:
    name = "localsynth-lyrics"
    display_name = "Meloyu 本地歌词引擎"
    engine_name = "localsynth-lyrics"

    # ---- 生成 ----
    def generate(self, theme: str, style_hint: str = "", mood: str | None = None,
                 language: str = "zh", sections: list[str] | None = None) -> dict:
        lang = "en" if language == "en" else "zh"
        rng = _rng_for("gen", theme, style_hint, mood, language)
        if not sections:
            sections = (["verse", "verse", "pre_chorus", "chorus", "chorus"] if lang == "zh"
                        else ["verse", "pre_chorus", "chorus", "chorus"])
        sections = sections[:12]
        mood_key = mood if mood and (mood in _IMAGERY["moods"]) else None
        bank = self._imagery_bank(mood_key, lang)
        group = self._pick_group(rng, theme, mood)

        lines_by_section: list[tuple[str, list[str]]] = []
        for sec in sections:
            count = 2 if sec in ("pre_chorus", "bridge") else 4
            lines = [self._fill_line(sec, rng, bank, group, theme, lang) for _ in range(count)]
            lines_by_section.append((sec, lines))

        lyrics = self._assemble(lines_by_section)
        structure = [{"section": sec, "line_count": len(lines)} for sec, lines in lines_by_section]

        alternatives = []
        for i in range(2):
            rng_alt = _rng_for("gen-alt", theme, style_hint, mood, language, i)
            if rng_alt.random() < 0.5:
                alt_group = self._pick_group(rng_alt, theme, mood, offset=i + 1)
                alt_lines = [(sec,
                              [self._fill_line(sec, rng_alt, bank, alt_group, theme, lang)
                               for _ in range(len(lines))])
                             for sec, lines in lines_by_section]
                alternatives.append({"lyrics": self._assemble(alt_lines)})

        return {"lyrics": lyrics, "structure": structure, "alternatives": alternatives}

    def _imagery_bank(self, mood_key: str | None, lang: str) -> dict[str, list[str]]:
        if lang == "en":
            return dict(_IMAGERY["en"])
        base = _IMAGERY["default"]
        bank = {"nouns": list(base["nouns"]), "places": list(base["places"]),
                "verbs": list(base["verbs"]), "adjs": ["温柔", "安静", "漫长", "滚烫", "轻盈"]}
        if mood_key:
            m = _IMAGERY["moods"][mood_key]
            bank["nouns"] = list(m["nouns"]) + bank["nouns"]
            bank["adjs"] = m.get("extra", bank["adjs"]) + bank["adjs"]
        return bank

    def _pick_group(self, rng: random.Random, theme: str, mood: str | None,
                    offset: int = 0) -> str:
        mood_groups = {"忧郁": ["一七", "灰堆"], "治愈": ["江阳", "怀来"], "热血": ["江阳", "遥条"],
                       "浪漫": ["言前", "遥条"], "紧张": ["一七", "姑苏"], "思念": ["人辰", "言前"],
                       "孤独": ["姑苏", "由求"], "宁静": ["中东", "发花"]}
        if mood and mood in mood_groups:
            return mood_groups[mood][(hashlib.sha256(theme.encode()).digest()[0] + offset) % 2]
        groups = list(_RHYMES["ending_words"].keys())
        return groups[rng.randrange(len(groups))]

    def _fill_line(self, section: str, rng: random.Random, bank: dict, group: str,
                   theme: str, lang: str) -> str:
        templates = _TEMPLATES[lang].get(section) or _TEMPLATES[lang]["verse"]
        tpl = templates[rng.randrange(len(templates))]
        words = _RHYMES["ending_words"][group]
        ending = words[rng.randrange(len(words))]
        nouns = bank["nouns"]
        places = bank["places"]
        verbs = bank["verbs"]
        adjs = bank.get("adjs", ["温柔"])
        theme_word = self._theme_word(theme, rng)

        def pick(lst):
            return lst[rng.randrange(len(lst))]

        line = tpl
        for _ in range(6):
            if "{A}" in line:
                line = line.replace("{A}", pick(nouns) if rng.random() > 0.35 else theme_word, 1)
            elif "{a}" in line:
                line = line.replace("{a}", pick(nouns) if rng.random() > 0.35 else theme_word, 1)
            elif "{b2}" in line:
                line = line.replace("{b2}", pick(adjs), 1)
            elif "{b}" in line:
                line = line.replace("{b}", pick(nouns), 1)
            elif "{p}" in line:
                line = line.replace("{p}", pick(places), 1)
            elif "{v}" in line:
                line = line.replace("{v}", pick(verbs), 1)
            elif "{E}" in line:
                line = line.replace("{E}", ending, 1)
            elif "{e}" in line:
                line = line.replace("{e}", ending, 1)
            else:
                break
        return line

    def _theme_word(self, theme: str, rng: random.Random) -> str:
        tokens = [t for t in re.split(r"[，,。.、\s]+", (theme or "").strip()) if 2 <= len(t) <= 6]
        if tokens:
            return tokens[rng.randrange(len(tokens))]
        return (theme or "")[:2] or "心事"

    def _assemble(self, lines_by_section) -> str:
        tag_map = {"verse": "[Verse]", "pre_chorus": "[Pre-Chorus]", "chorus": "[Chorus]",
                   "bridge": "[Bridge]", "intro": "[Intro]", "outro": "[Outro]"}
        parts = []
        for sec, lines in lines_by_section:
            if sec in ("intro", "outro") and not lines:
                continue
            parts.append(tag_map.get(sec, "[Verse]"))
            parts.extend(lines)
        return "\n".join(parts)

    # ---- 润色 ----
    def polish(self, lyrics: str, target_section: str | None = None,
               style_hint: str = "", locked_lines: list[int] | None = None) -> dict:
        rng = _rng_for("polish", lyrics, target_section, style_hint)
        locked = set(locked_lines or [])
        parsed, _ = parse_lyrics(lyrics)
        changes: list[dict] = []
        polished_sections: list[str] = []
        out_lines: list[str] = []
        line_no = 0
        for sec, lines in parsed:
            section_touched = False
            new_lines = []
            # 主韵组：段内出现最多的组
            groups = [rhyme_group_of(final_of(ln[-1])) for ln in lines if ln]
            groups = [g for g in groups if g]
            main_g: str | None = None
            if groups:
                main_g = max(set(groups), key=groups.count)
            for ln in lines:
                line_no += 1
                if line_no in locked or (target_section and sec != target_section):
                    new_lines.append(ln)
                    continue
                new_ln = ln
                # 1) 出韵行：换尾词
                g = rhyme_group_of(final_of(ln[-1])) if ln else None
                if main_g and g and g != main_g:
                    words = _RHYMES["ending_words"][main_g]
                    repl = words[rng.randrange(len(words))]
                    if len(new_ln) > 3:
                        new_ln = new_ln[:-2] + repl if len(new_ln) > 5 else new_ln[:-1] + repl[-1]
                # 2) 意象替换（重复名词换同义词）
                base = _IMAGERY["default"]["nouns"]
                for noun in base:
                    if noun in new_ln and rng.random() < 0.5:
                        alt = base[rng.randrange(len(base))]
                        if alt != noun:
                            new_ln = new_ln.replace(noun, alt, 1)
                        break
                if new_ln != ln:
                    changes.append({"line_no": line_no, "before": ln, "after": new_ln})
                    section_touched = True
                new_lines.append(new_ln)
            if section_touched:
                polished_sections.append(sec)
            out_lines.append((sec, new_lines))
        return {"lyrics": self._assemble(out_lines), "changes": changes,
                "polished_sections": polished_sections}

    # ---- 押韵/重音检查 ----
    def rhyme_check(self, lyrics: str) -> dict:
        parsed, _ = parse_lyrics(lyrics)
        all_groups: list[str] = []
        sections_out = []
        suggestions: list[dict] = []
        line_no = 0
        sec_line_counts: list[tuple[str, int]] = []
        for sec, lines in parsed:
            lines_out = []
            for ln in lines:
                line_no += 1
                tail = ln[-1] if ln else ""
                fin = final_of(tail)
                grp = rhyme_group_of(fin)
                if grp:
                    all_groups.append(grp)
                lines_out.append({"line_no": line_no, "text": ln, "tail_char": tail,
                                  "tail_pinyin": pinyin_of(tail),
                                  "rhyme_group": fin or "a", "in_rhyme": None})
            sec_line_counts.append((sec, len(lines)))
            sections_out.append({"section": sec, "lines": lines_out})
        main_group = max(set(all_groups), key=all_groups.count) if all_groups else None
        main_final = None
        for sec in sections_out:
            for ln in sec["lines"]:
                ln["in_rhyme"] = (main_group is None
                                  or rhyme_group_of(ln["rhyme_group"]) == main_group)
        # main_rhyme_group：主组内最常见的 final
        if main_group:
            finals = [ln["rhyme_group"] for sec in sections_out for ln in sec["lines"]
                      if rhyme_group_of(ln["rhyme_group"]) == main_group and ln["rhyme_group"]]
            main_final = max(set(finals), key=finals.count) if finals else None
        off_count = 0
        for sec in sections_out:
            for idx, ln in enumerate(sec["lines"]):
                if ln["in_rhyme"] is False:
                    off_count += 1
                    # en 侧只嵌拉丁韵尾（rhyme_group/main_final 本就是 final 如 "ang"），
                    # 不嵌中文辙名（江阳/怀来），保证英文界面零中文
                    suggestions.append({
                        "line_no": ln["line_no"], "type": "rhyme",
                        "message": tr(f"尾字「{ln['tail_char']}」属 "
                                   f"{rhyme_group_of(ln['rhyme_group']) or '未知'} 辙，与主韵 "
                                   f"{main_group} 不一致，建议换 {main_group} 辙词",
                                   f'Tail char "{ln["tail_char"]}" ends in '
                                   f'"{ln["rhyme_group"]}", which differs from the main '
                                   f'rhyme "{main_final}"; consider a word ending in '
                                   f'"{main_final}"')})
                # 重音：每段末行的句尾双字词建议落长音
                text = ln["text"]
                if idx == len(sec["lines"]) - 1 and re.search(r"[\u4e00-\u9fff]{2}$", text):
                    last2 = text[-2:]
                    suggestions.append({
                        "line_no": ln["line_no"], "type": "stress",
                        "message": tr(f"「{last2}」为句尾双字词，建议落长音",
                                   f'"{last2}" ends the line with a two-char word; let it land on a long note')})
        counts = [c for _, c in sec_line_counts if c > 0]
        if counts and max(counts) - min(counts) >= 3:
            suggestions.append({
                "line_no": 1, "type": "structure",
                "message": tr("段落行数不均衡（相差 ≥3 行），建议各段行数对齐",
                            "Sections have unbalanced line counts (diff >= 3); align them")})
        return {"sections": sections_out, "main_rhyme_group": main_final,
                "off_rhyme_count": off_count, "suggestions": suggestions}

    # ---- 标签补全 ----
    def complete_tags(self, lyrics: str) -> dict:
        parsed, has_tags = parse_lyrics(lyrics)
        detected: list[dict] = []
        line_no = 0
        if has_tags:
            for sec, lines in parsed:
                start = line_no + 1
                line_no += len(lines)
                detected.append({"section": sec, "line_range": [start, max(start, line_no)]})
            return {"lyrics": lyrics, "inferred": False, "detected": detected}
        # 无标签 → 模板推断（每 4 行一段）
        all_lines = [ln for _, lines in parsed for ln in lines]
        if not all_lines:
            all_lines = [lyrics.strip()] if lyrics.strip() else []
        n = len(all_lines)
        if n == 0:
            return {"lyrics": lyrics, "inferred": False, "detected": []}
        if n <= 4:
            layout = [("verse", all_lines)]
        elif n <= 8:
            layout = [("verse", all_lines[: max(1, n // 2)]),
                      ("chorus", all_lines[max(1, n // 2):])]
        else:
            layout = [("verse", all_lines[: n // 3]),
                      ("pre_chorus", all_lines[n // 3: 2 * n // 3][:2]),
                      ("chorus", all_lines[2 * n // 3:])]
        parts = []
        line_no = 0
        for sec, lines in layout:
            tag = {"verse": "[Verse]", "pre_chorus": "[Pre-Chorus]", "chorus": "[Chorus]"}.get(sec)
            parts.append(tag)
            parts.extend(lines)
            start = line_no + 1
            line_no += len(lines)
            detected.append({"section": sec, "line_range": [start, max(start, line_no)]})
        return {"lyrics": "\n".join(parts), "inferred": True, "detected": detected}


def normalize_tag(tag: str) -> str | None:
    key = tag.lower().strip()
    return SECTION_ALIASES.get(key)


__all__ = ["LocalLyricsProvider", "check_sensitive", "rhyme_group_of", "final_of",
           "pinyin_of", "TAG_RE"]
