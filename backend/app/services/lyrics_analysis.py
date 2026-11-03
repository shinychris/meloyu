"""歌词确定性分析工具：押韵/重音检查与结构标签补全（非引擎、非 AI）。

pypinyin 韵组为确定性声学计算，交给 LLM 反而不可靠、更慢，故独立成模块，
供 /lyrics/rhyme-check 与 /lyrics/complete-tags 使用（原属本地歌词规则引擎，
2026-11-01 随引擎一并移除后按工具保留）。同步、无状态、不扣积分。
"""
from __future__ import annotations

import re

from pypinyin import Style, pinyin

from app.core.i18n import tr
from app.synth.structure import parse_lyrics

# final → 十三辙（语言常量，随模块内置）
_RHYME_GROUPS: dict[str, list[str]] = {
    "发花": ["a", "ia", "ua"],
    "梭波": ["o", "e", "uo"],
    "乜斜": ["ie", "ve"],
    "一七": ["i", "v", "er"],
    "姑苏": ["u"],
    "怀来": ["ai", "uai"],
    "灰堆": ["ei", "ui"],
    "遥条": ["ao", "iao"],
    "由求": ["ou", "iu"],
    "言前": ["an", "ian", "uan", "van"],
    "人辰": ["en", "in", "un", "vn"],
    "江阳": ["ang", "iang", "uang"],
    "中东": ["eng", "ing", "ong", "iong"],
}
_FINAL_TO_GROUP: dict[str, str] = {f: g for g, finals in _RHYME_GROUPS.items()
                                   for f in finals}


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


def rhyme_check(lyrics: str) -> dict:
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


def complete_tags(lyrics: str) -> dict:
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
