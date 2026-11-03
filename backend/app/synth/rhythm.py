"""阶段④：鼓组模式 + 贝斯线（密度参数与负向提示调制）。"""
from __future__ import annotations

import numpy as np

from app.core.i18n import tr
from app.synth.ir import BAR_QUARTER_UNITS, DrumHit, Note, SongIR

# 16 分网格位置（4/4 用 16 格；3/4 与 6/8 用 12 格）
PATTERNS: dict[str, dict[str, list[int]]] = {
    "pop":     {"kick": [0, 8], "snare": [4, 12], "hat": [0, 2, 4, 6, 8, 10, 12, 14]},
    "guofeng": {"kick": [0, 8], "snare": [4, 12], "hat": [2, 6, 10, 14]},
    "edm":     {"kick": [0, 4, 8, 12], "snare": [4, 12], "hat": [2, 6, 10, 14]},
    "hiphop":  {"kick": [0, 10], "snare": [4, 12], "hat": [0, 3, 6, 8, 11, 14]},  # swing 感
    "lofi":    {"kick": [0, 10], "snare": [4, 12], "hat": [2, 6, 10, 14]},
    "rock":    {"kick": [0, 8, 10], "snare": [4, 12], "hat": [2, 6, 10, 14]},
}

GRID = {"4/4": 16, "3/4": 12, "6/8": 12}


def _neg_hit(negative_prompt: str, keywords: list[str]) -> bool:
    text = (negative_prompt or "")
    return any(k in text for k in keywords)


def build_rhythm(ir: SongIR, rng: np.random.Generator) -> None:
    req = ir.req
    family = ir.style_family
    grid = GRID[req.time_signature]
    beats_per_bar = BAR_QUARTER_UNITS[req.time_signature]
    step_sec = (60.0 / req.bpm) * beats_per_bar / grid
    density = max(0.0, min(1.0, req.instrument_density / 100.0))

    no_drums = _neg_hit(req.negative_prompt, ["不要鼓", "无鼓", "不要打击", "no drum", "不要鼓机"])
    no_bass = _neg_hit(req.negative_prompt, ["不要贝斯", "无贝斯", "不要低音", "no bass",
                                             "不要808", "不要 808"])
    if no_drums:
        ir.applied_negative.append(tr("不要鼓机/鼓组", "no drums/percussion"))
    if no_bass:
        ir.applied_negative.append(tr("不要贝斯/808", "no bass/808"))
    if "电音人声" in (req.negative_prompt or ""):
        ir.applied_negative.append(tr("不要电音人声", "no synth-tuned vocals"))

    pat = PATTERNS[family]
    drums: list[DrumHit] = []
    bass: list[Note] = []

    for sp in ir.sections:
        for b in range(sp.bars):
            bar = sp.start_bar + b
            chord = ir.chords[bar] if bar < len(ir.chords) else None
            # ---- 鼓 ----
            if not no_drums:
                thin = sp.energy < 0.45  # 低能量段抽稀（intro 只留 hat）
                for kind, positions in pat.items():
                    for pos in positions:
                        if pos >= grid:
                            continue
                        if kind == "hat":
                            prob = 0.35 + 0.6 * density * sp.energy
                            if thin and sp.section == "intro" and kind != "hat":
                                continue
                        else:
                            prob = 1.0 if not thin else (0.5 if kind == "kick" else 0.0)
                        if rng.random() > prob:
                            continue
                        vel = (0.7 + 0.3 * sp.energy) if kind != "hat" else (0.3 + 0.4 * density)
                        drums.append(DrumHit(start=bar * beats_per_bar * (60.0 / req.bpm)
                                             + pos * step_sec, kind=kind, vel=vel))
                # 段末小节 fill（snare 密集），仅高能量段
                if sp.energy >= 0.9 and b == sp.bars - 1 and rng.random() < density:
                    for pos in range(grid - 4, grid):
                        drums.append(DrumHit(start=bar * beats_per_bar * (60.0 / req.bpm)
                                             + pos * step_sec, kind="snare", vel=0.5))
            # ---- 贝斯 ----
            if not no_bass and chord is not None:
                root = chord.bass_midi
                fifth = root + 7
                bar_start = bar * beats_per_bar * (60.0 / req.bpm)
                beat = 60.0 / req.bpm
                if family == "hiphop":
                    # 808 长音
                    dur = beats_per_bar * beat * 0.98
                    bass.append(Note(start=bar_start, dur=dur, midi=root,
                                     vel=0.55 + 0.35 * sp.energy))
                elif family == "edm":
                    # 8 分 off-beat
                    step = beat / 2
                    n_steps = int(beats_per_bar * 2)
                    for i in range(n_steps):
                        if i % 2 == 1 and rng.random() < 0.3 + 0.6 * density:
                            bass.append(Note(start=bar_start + i * step, dur=step * 0.9,
                                             midi=root, vel=0.5 + 0.3 * sp.energy))
                elif family == "rock":
                    # 八分连续根音
                    step = beat / 2
                    n_steps = int(beats_per_bar * 2)
                    for i in range(n_steps):
                        if rng.random() < 0.5 + 0.5 * density:
                            bass.append(Note(start=bar_start + i * step, dur=step * 0.9,
                                             midi=root, vel=0.5 + 0.3 * sp.energy))
                else:
                    # pop 等：根音+五度 四分
                    n_beats = int(beats_per_bar)
                    for i in range(n_beats):
                        if i in (0, n_beats // 2) or rng.random() < 0.4 * density:
                            midi = root if i % 2 == 0 else fifth
                            if sp.energy < 0.4 and i not in (0,):
                                continue
                            bass.append(Note(start=bar_start + i * beat, dur=beat * 0.9,
                                             midi=midi, vel=0.5 + 0.3 * sp.energy))
    ir.drums = drums
    ir.bass_notes = bass
