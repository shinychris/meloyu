"""V1.1 派生编辑引擎：extend 续写 / variant 同构变奏 / regen-section 段落重生成。

设计要点（契约 §5.5~5.7 计划语义）：
- 确定性：派生种子 = SHA-256("{base_seed}:{op}:{extra}") 低 32 位；全程 seeded PCG64，
  音频内容路径禁 random/time。同（源候选, 操作, 参数）→ 逐字节相同产物。
- extend：续写段独立渲染（同 key/BPM/风格/人声设定，首小节沿用原曲末小节和弦），
  与原音频等功率交叉淡化拼接（≥50ms，无爆音）。
- variant：段落划分/时长逐段复用原候选（重建结构并校验一致），和声/旋律/编曲
  以新 style_prompt（换和弦库/鼓型/配器）整曲重渲染。
- regen-section：整曲重渲染后，非目标段时间范围逐样本复制回原候选采样（字节级不变，
  同名其他出现同属非目标段）；边界融合窗只落在目标段内部，保证非目标段 sha256 不变（FR-6）。
"""
from __future__ import annotations

import hashlib
from dataclasses import replace

import numpy as np

from app.core.i18n import tr
from app.synth import harmony as harmony_mod
from app.synth import melody as melody_mod
from app.synth import rhythm as rhythm_mod
from app.synth import structure as structure_mod
from app.synth.ir import SAMPLE_RATE, SectionPlan, SongIR, SongRequest

# extend 拼接交叉淡化时长（契约要求 ≥50ms）
CROSSFADE_SEC = 0.064
# regen-section 选区边界融合窗（只覆盖选区内部，不触碰非选区字节）
BLEND_SEC = 0.06

_MASK32 = 0xFFFFFFFF


def derive_op_seed(base_seed: int, op: str, extra: str = "") -> int:
    """派生种子：仅由（源候选种子, 操作, 参数摘要）决定，可复现。"""
    digest = hashlib.sha256(f"{base_seed}:{op}:{extra}".encode()).digest()
    return int.from_bytes(digest[:4], "big") & _MASK32


def make_rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(np.random.PCG64(seed & _MASK32))


def rebuild_ir(req: SongRequest, seed: int, *, with_notes: bool = True) -> SongIR:
    """从 (params, seed) 确定性重建 SongIR（阶段①~④，不渲染音频）。

    原生成同 seed 走相同 rng 消费序列（harmony→melody→rhythm），重建的
    音符事件与原候选逐一一致；with_notes=False 只重建结构（段落/行分配）。
    """
    ir = SongIR(req=req, seed=seed)
    parsed, has_tags = structure_mod.parse_lyrics(req.lyrics)
    structure_mod.build_structure(ir, parsed, has_tags)
    if with_notes:
        rng = make_rng(seed)
        harmony_mod.build_harmony(ir, rng)
        melody_mod.compose_melody(ir, rng)
        rhythm_mod.build_rhythm(ir, rng)
    return ir


def sections_from_structure(structure: list[dict]) -> list[SectionPlan]:
    """存库 structure JSON → SectionPlan（能量按段落类型查表，行留空走器乐填充）。"""
    plans = []
    for seg in structure or []:
        sec = str(seg.get("section", "verse"))
        plans.append(SectionPlan(
            section=sec, start_bar=int(seg.get("start_bar", 0)),
            bars=max(1, int(seg.get("bars", 1))),
            energy=structure_mod.SECTION_ENERGY.get(sec, 0.5),
        ))
    return plans


def structure_matches(ir: SongIR, stored: list[dict]) -> bool:
    """重建结构与存库候选 structure 逐段比对（section + bars）。"""
    if len(ir.sections) != len(stored or []):
        return False
    return all(sp.section == seg.get("section") and sp.bars == int(seg.get("bars", -1))
               for sp, seg in zip(ir.sections, stored, strict=True))


def build_tail_ir(req_ext: SongRequest, seed_rng: np.random.Generator,
                  base_ir: SongIR) -> SongIR:
    """extend 续写段 IR：单段（尾段类型延续），首小节沿用原曲末小节和弦。

    req_ext.duration_sec 为续写秒数；歌词为空 → 器乐化收尾（outro 语义）。
    """
    ir = SongIR(req=req_ext, seed=req_ext.seed)
    quarter = structure_mod.BAR_QUARTER_UNITS[req_ext.time_signature]
    bar_sec = quarter * 60.0 / req_ext.bpm
    bars = max(1, int(round(req_ext.duration_sec / bar_sec)))
    tail_type = base_ir.sections[-1].section if base_ir.sections else "outro"
    ir.sections = [SectionPlan(section=tail_type, start_bar=0, bars=bars,
                               energy=structure_mod.SECTION_ENERGY.get(tail_type, 0.35))]
    ir.total_bars = bars
    ir.bar_sec = bar_sec
    ir.style_family = base_ir.style_family
    harmony_mod.build_harmony(ir, seed_rng)
    if base_ir.chords and ir.chords:
        # 调性衔接：续写首小节 = 原曲末小节和弦（bar 归零）
        ir.chords[0] = replace(base_ir.chords[-1], bar=0)
    melody_mod.compose_melody(ir, seed_rng)
    rhythm_mod.build_rhythm(ir, seed_rng)
    return ir


def merge_ir_for_midi(base_ir: SongIR, ext_ir: SongIR) -> SongIR:
    """extend 全曲 MIDI 用 IR：原曲事件 + 续写段事件（时间轴平移原曲总长）。"""
    ir = SongIR(req=base_ir.req, seed=ext_ir.seed)
    off_bars = base_ir.total_bars
    off_sec = base_ir.total_sec
    ir.sections = list(base_ir.sections) + [
        replace(sp, start_bar=sp.start_bar + off_bars) for sp in ext_ir.sections]
    ir.total_bars = off_bars + ext_ir.total_bars
    ir.bar_sec = base_ir.bar_sec
    ir.chords = list(base_ir.chords) + [
        replace(c, bar=c.bar + off_bars) for c in ext_ir.chords]
    ir.melody = list(base_ir.melody) + [replace(n, start=n.start + off_sec)
                                        for n in ext_ir.melody]
    ir.vocal_notes = list(base_ir.vocal_notes) + [replace(n, start=n.start + off_sec)
                                                  for n in ext_ir.vocal_notes]
    ir.bass_notes = list(base_ir.bass_notes) + [replace(n, start=n.start + off_sec)
                                                for n in ext_ir.bass_notes]
    ir.drums = list(base_ir.drums) + [replace(h, start=h.start + off_sec)
                                      for h in ext_ir.drums]
    return ir


def build_variant_ir(req_variant: SongRequest, base_ir: SongIR,
                     stored_structure: list[dict],
                     rng: np.random.Generator) -> SongIR:
    """variant IR：结构（含歌词行分配）逐段沿用原曲，和声/旋律/编曲按新风格重作。"""
    ir = SongIR(req=req_variant, seed=req_variant.seed)
    if structure_matches(base_ir, stored_structure):
        ir.sections = [replace(sp) for sp in base_ir.sections]
    else:  # 防御：引擎结构推断与存库不一致时以存库 structure 为准（逐段一致优先）
        ir.sections = sections_from_structure(stored_structure)
    ir.total_bars = sum(sp.bars for sp in ir.sections)
    quarter = structure_mod.BAR_QUARTER_UNITS[req_variant.time_signature]
    ir.bar_sec = quarter * 60.0 / req_variant.bpm
    harmony_mod.build_harmony(ir, rng)
    melody_mod.compose_melody(ir, rng)
    rhythm_mod.build_rhythm(ir, rng)
    return ir


def section_occurrence_index(structure: list[dict], section: str,
                             occurrence: int) -> int | None:
    """section 第 occurrence 次出现（1 起始）在 structure 中的下标；越界返回 None。"""
    idxs = [i for i, seg in enumerate(structure or [])
            if str(seg.get("section")) == section]
    if 1 <= occurrence <= len(idxs):
        return idxs[occurrence - 1]
    return None


def regenerate_sections(base_ir: SongIR, section: str, occurrence: int,
                        rng: np.random.Generator) -> SongIR:
    """复制 base_ir，仅重生成 section 第 occurrence 次出现的那个段落。

    其余段落（含同名其他出现）的音符事件对象原样保留（MIDI 导出时逐事件一致）。
    """
    matches = [sp for sp in base_ir.sections if sp.section == section]
    if not 1 <= occurrence <= len(matches):
        raise ValueError(tr(f"occurrence 越界：段落 {section} 共出现 {len(matches)} 次",
                         f"occurrence out of range: section {section} appears "
                         f"{len(matches)} time(s)"))
    selected = [matches[occurrence - 1]]
    ir = SongIR(req=base_ir.req, seed=base_ir.seed)
    ir.style_family = base_ir.style_family
    ir.inferred_structure = base_ir.inferred_structure
    ir.sections = [replace(sp) for sp in base_ir.sections]
    ir.total_bars = base_ir.total_bars
    ir.bar_sec = base_ir.bar_sec
    ir.applied_negative = list(base_ir.applied_negative)
    ir.chords = list(base_ir.chords)
    ir.melody = list(base_ir.melody)
    ir.vocal_notes = list(base_ir.vocal_notes)
    ir.bass_notes = list(base_ir.bass_notes)
    ir.drums = list(base_ir.drums)

    # 仅含选区段的 IR（start_bar 保持原绝对位置），以传入 rng 重作三阶段
    ir_sel = SongIR(req=base_ir.req, seed=base_ir.seed)
    ir_sel.style_family = base_ir.style_family
    ir_sel.sections = [replace(sp) for sp in selected]
    ir_sel.total_bars = base_ir.total_bars
    ir_sel.bar_sec = base_ir.bar_sec
    harmony_mod.build_harmony(ir_sel, rng)
    melody_mod.compose_melody(ir_sel, rng)
    rhythm_mod.build_rhythm(ir_sel, rng)

    bar_ranges = [(sp.start_bar, sp.start_bar + sp.bars) for sp in selected]
    sec_ranges = [(a * ir.bar_sec, b * ir.bar_sec) for a, b in bar_ranges]

    def hit_bar(bar: int) -> bool:
        return any(a <= bar < b for a, b in bar_ranges)

    def hit_sec(t: float) -> bool:
        return any(a <= t < b - 1e-9 for a, b in sec_ranges)

    # 和弦按 bar 位置对齐（render/rhythm 以 ir.chords[bar] 索引访问，需连续填满）
    merged: list = [None] * ir.total_bars
    for c in ir.chords:
        if not hit_bar(c.bar):
            merged[c.bar] = c
    for c in ir_sel.chords:
        merged[c.bar] = c
    if any(c is None for c in merged):
        raise ValueError(tr("段落重生成后和弦未覆盖全部小节",
                            "regenerated section chords do not cover all bars"))
    ir.chords = [c for c in merged if c is not None]

    for attr in ("melody", "vocal_notes", "bass_notes", "drums"):
        kept = [n for n in getattr(ir, attr) if not hit_sec(n.start)]
        getattr(ir, attr)[:] = sorted(kept + list(getattr(ir_sel, attr)),
                                      key=lambda n: n.start)
    return ir


# ---------- 波形级拼接 ----------

def crossfade_concat(a: np.ndarray, b: np.ndarray, xf: int) -> np.ndarray:
    """等功率交叉淡化拼接：a 尾与 b 头在 xf 样本窗内融合（拼接点无爆音）。"""
    if xf <= 0 or len(a) <= xf or len(b) <= xf:
        return np.concatenate([a, b])
    t = np.arange(xf, dtype=np.float64) / xf
    fade_a = np.cos(t * np.pi / 2)
    fade_b = np.sin(t * np.pi / 2)
    return np.concatenate([
        a[: len(a) - xf],
        a[len(a) - xf:] * fade_a + b[:xf] * fade_b,
        b[xf:],
    ])


def structure_sample_ranges(structure: list[dict], n_samples: int) -> list[tuple[int, int]]:
    """存库 structure（秒，2 位小数）→ 连续采样区间 [(a,b)]，与 API 暴露值一致。

    边界取 int(round(sec * SAMPLE_RATE))——冒烟测试按同公式切片比对 sha256。
    """
    ranges: list[tuple[int, int]] = []
    prev = 0
    for seg in structure or []:
        a = int(round(float(seg.get("start_sec", 0.0)) * SAMPLE_RATE))
        b = int(round(float(seg.get("end_sec", 0.0)) * SAMPLE_RATE))
        a = max(0, min(a, n_samples))
        b = max(a, min(b, n_samples))
        a = prev  # 保证区间连续无缝（首段从 0 起）
        b = max(a, b)
        ranges.append((a, b))
        prev = b
    if ranges:
        a, _ = ranges[-1]
        ranges[-1] = (a, n_samples)  # 末段补到文件实际长度
    return ranges


def splice_regen(rendered: np.ndarray, orig: np.ndarray, structure: list[dict],
                 target_index: int) -> np.ndarray:
    """regen-section 波形装配：非目标段逐样本复制原候选，目标段保留重渲染内容。

    边界融合窗（BLEND_SEC）只落在目标段内部：窗内由原内容淡入/淡出到重渲染内容，
    至边界点精确等于原样本 → 非目标段字节级不变且拼接处连续无爆音。
    target_index 为 structure 下标（由 section + occurrence 解析，同名其他出现不选中）。
    """
    if len(rendered) != len(orig):
        raise ValueError(tr(f"长度不一致：渲染 {len(rendered)} vs 原始 {len(orig)}",
                            f"length mismatch: rendered {len(rendered)} vs original "
                            f"{len(orig)}"))
    n = len(orig)
    out = np.array(rendered, dtype=np.float64, copy=True)
    ranges = structure_sample_ranges(structure, n)
    selected = [i == target_index for i in range(len(ranges))]
    blend = int(BLEND_SEC * SAMPLE_RATE)

    for i, (a, b) in enumerate(ranges):
        if selected[i]:
            continue
        out[a:b] = orig[a:b]  # 非选区：字节级复制原候选采样
    for i, (a, b) in enumerate(ranges):
        if not selected[i]:
            continue
        w = min(blend, max(0, (b - a) // 4))
        if w <= 0:
            continue
        prev_kept = i > 0 and not selected[i - 1]  # 左邻为保留段 → 头部融合
        if prev_kept and a > 0:
            t = np.arange(w, dtype=np.float64) / w
            out[a:a + w] = orig[a:a + w] * (1.0 - t) + rendered[a:a + w] * t
        next_kept = i + 1 < len(ranges) and not selected[i + 1]  # 右邻为保留段 → 尾部融合
        if next_kept and b < n:
            t = np.arange(w, dtype=np.float64) / w
            out[b - w:b] = rendered[b - w:b] * t + orig[b - w:b] * (1.0 - t)
    return out
