"""阶段①：结构标签解析与自动推断（架构 §7.3）。

单一事实来源：providers/lyrics 的 complete-tags 复用本模块。
"""
from __future__ import annotations

import re

from app.synth.ir import BAR_QUARTER_UNITS, SectionPlan, SongIR

TAG_RE = re.compile(r"^\[\s*([^\]]+?)\s*\]$")
# 段落规范顺序（/system/meta structure_tags 与前端标签条目顺序的单一事实来源）
SECTION_ORDER = ("intro", "verse", "pre_chorus", "chorus", "post_chorus", "refrain",
                 "bridge", "interlude", "drop", "breakdown", "rap", "spoken",
                 "ad_lib", "solo", "outro")
# 段落 → 规范标签（lyrics_local/_llm 组装与 meta 下发共用；未知段不做映射）
SECTION_TAG: dict[str, str] = {
    "intro": "[Intro]", "verse": "[Verse]", "pre_chorus": "[Pre-Chorus]",
    "chorus": "[Chorus]", "post_chorus": "[Post-Chorus]", "refrain": "[Refrain]",
    "bridge": "[Bridge]", "interlude": "[Interlude]", "drop": "[Drop]",
    "breakdown": "[Breakdown]", "rap": "[Rap]", "spoken": "[Spoken]",
    "ad_lib": "[Ad-Lib]", "solo": "[Solo]", "outro": "[Outro]",
}

# 中英文别名 → 归一化段落枚举（大小写不敏感；v0.12.1 扩全主流段落）
SECTION_ALIASES: dict[str, str] = {
    "intro": "intro", "前奏": "intro",
    "verse": "verse", "verse1": "verse", "verse2": "verse", "verse3": "verse",
    "verse4": "verse", "verse 1": "verse", "verse 2": "verse", "verse 3": "verse",
    "verse 4": "verse", "主歌": "verse",
    "pre-chorus": "pre_chorus", "prechorus": "pre_chorus", "pre chorus": "pre_chorus",
    "pre_chorus": "pre_chorus",
    "pre": "pre_chorus", "导歌": "pre_chorus", "预副歌": "pre_chorus",
    "chorus": "chorus", "hook": "chorus", "chorus1": "chorus", "chorus2": "chorus",
    "chorus3": "chorus", "chorus4": "chorus", "chorus 1": "chorus",
    "chorus 2": "chorus", "chorus 3": "chorus", "chorus 4": "chorus", "副歌": "chorus",
    "post-chorus": "post_chorus", "postchorus": "post_chorus",
    "post chorus": "post_chorus", "post_chorus": "post_chorus",
    "后副歌": "post_chorus", "副歌后": "post_chorus",
    "refrain": "refrain", "叠句": "refrain",
    "bridge": "bridge", "桥段": "bridge",
    "interlude": "interlude", "间奏": "interlude",
    "drop": "drop", "爆点": "drop",
    "breakdown": "breakdown", "分解段": "breakdown", "崩解段": "breakdown",
    "rap": "rap", "rap verse": "rap", "rapverse": "rap", "rap_verse": "rap",
    "说唱": "rap", "说唱段": "rap",
    "spoken": "spoken", "spoken word": "spoken", "spoken_word": "spoken",
    "念白": "spoken", "独白": "spoken",
    "ad-lib": "ad_lib", "adlib": "ad_lib", "ad lib": "ad_lib", "ad_lib": "ad_lib",
    "即兴衬词": "ad_lib", "和声衬词": "ad_lib",
    "solo": "solo", "guitar solo": "solo", "instrumental": "solo",
    "独奏": "solo", "器乐段": "solo",
    "outro": "outro", "尾奏": "outro",
}

# 段落基础小节与能量权重（架构 §7.3；新段落按其主流音乐功能定档）
SECTION_BASE_BARS = {"intro": 4, "verse": 8, "pre_chorus": 4, "chorus": 8,
                     "post_chorus": 4, "refrain": 4, "bridge": 4, "interlude": 4,
                     "drop": 8, "breakdown": 4, "rap": 8, "spoken": 4,
                     "ad_lib": 2, "solo": 4, "outro": 4}
SECTION_ENERGY = {"intro": 0.3, "verse": 0.5, "pre_chorus": 0.65, "chorus": 1.0,
                  "post_chorus": 0.85, "refrain": 0.7, "bridge": 0.4,
                  "interlude": 0.35, "drop": 1.0, "breakdown": 0.45, "rap": 0.75,
                  "spoken": 0.35, "ad_lib": 0.8, "solo": 0.8, "outro": 0.35}

# 无标签自动推断模板（按请求时长）
TEMPLATE_FULL = ["intro", "verse", "pre_chorus", "chorus",
                 "verse", "pre_chorus", "chorus", "bridge", "chorus", "outro"]
TEMPLATE_MEDIUM = ["intro", "verse", "chorus", "outro"]
TEMPLATE_LOOP = ["intro", "chorus", "outro"]


def parse_lyrics(lyrics: str) -> tuple[list[tuple[str, list[str]]], bool]:
    """解析歌词结构标签。

    返回 ([(section, [lines])], has_tags)。
    - 标签行不进入歌词行；标签前出现的行归入 verse。
    - 无任何有效标签时 has_tags=False，lines 为全文非空行。
    - 空段落保留（v0.12.1：[Drop]/[Solo] 等纯器乐段的规范用法即标签下无
      歌词行，合成管线对无行段落走器乐主旋律，不因空行丢段）。
    """
    sections: list[tuple[str, list[str]]] = []
    has_tags = False
    current = "verse"
    pending_lines: list[str] = []

    def flush():
        nonlocal pending_lines
        if has_tags or pending_lines:
            sections.append((current, pending_lines))
        pending_lines = []

    for raw in (lyrics or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = TAG_RE.match(line)
        if m:
            key = m.group(1).lower().strip()
            sec = SECTION_ALIASES.get(key) or SECTION_ALIASES.get(m.group(1).strip())
            if sec:
                flush()
                current = sec
                has_tags = True
                continue
            # 未知标签当普通文本处理
        pending_lines.append(line)
    flush()

    if not has_tags:
        all_lines = [ln for _, lines in sections for ln in lines]
        return ([("verse", all_lines)] if all_lines else []), False
    return sections, True


def _template_for(duration_sec: float) -> list[str]:
    if duration_sec >= 150:
        return list(TEMPLATE_FULL)
    if duration_sec >= 60:
        return list(TEMPLATE_MEDIUM)
    return list(TEMPLATE_LOOP)


def plan_sections(parsed: list[tuple[str, list[str]]], has_tags: bool,
                  bpm: int, time_signature: str, duration_sec: int) -> tuple[list[SectionPlan], bool]:
    """产出段落计划：小节数按权重归一分配，总时长与请求偏差 ≤ ±5%。"""
    quarter_units = BAR_QUARTER_UNITS[time_signature]
    bar_sec = quarter_units * 60.0 / bpm
    bars_total = max(4, round(duration_sec / bar_sec))
    # ±5% 约束修正
    while bars_total * bar_sec > duration_sec * 1.05:
        bars_total -= 1
    while bars_total * bar_sec < duration_sec * 0.95:
        bars_total += 1

    inferred = not has_tags
    if inferred or not parsed:
        seq = _template_for(float(duration_sec))
        parsed = [(sec, []) for sec in seq]

    base_total = sum(SECTION_BASE_BARS[s] for s, _ in parsed)
    plans: list[SectionPlan] = []
    for sec, lines in parsed:
        bars = max(1, round(SECTION_BASE_BARS[sec] * bars_total / base_total))
        plans.append(SectionPlan(section=sec, start_bar=0, bars=bars,
                                 energy=SECTION_ENERGY[sec], lines=list(lines)))
    # 误差修正到最后一段
    diff = bars_total - sum(p.bars for p in plans)
    if plans:
        plans[-1].bars = max(1, plans[-1].bars + diff)
    cursor = 0
    for p in plans:
        p.start_bar = cursor
        cursor += p.bars
    return plans, inferred


def build_structure(ir: SongIR, parsed: list[tuple[str, list[str]]], has_tags: bool) -> None:
    plans, inferred = plan_sections(
        parsed, has_tags, ir.req.bpm, ir.req.time_signature, ir.req.duration_sec
    )
    ir.sections = plans
    ir.inferred_structure = inferred
    ir.total_bars = sum(p.bars for p in plans)
    quarter_units = BAR_QUARTER_UNITS[ir.req.time_signature]
    ir.bar_sec = quarter_units * 60.0 / ir.req.bpm
