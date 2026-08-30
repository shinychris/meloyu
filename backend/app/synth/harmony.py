"""阶段②：风格化和弦进行库与选择（架构 §7.4）。

级数以「调内音级索引（0 起）」或「半音偏移（rock 的 bVII=10）」表达。
"""
from __future__ import annotations

import numpy as np

from app.synth.ir import ChordBar, SongIR

TONIC_PC = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
            "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}

MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]

# 大 / 小调顺阶三和弦品质
MAJOR_TRIADS = ["maj", "min", "min", "maj", "maj", "min", "dim"]
MINOR_TRIADS = ["min", "dim", "maj", "min", "min", "maj", "maj"]

ROMAN_MAJOR = ["I", "ii", "iii", "IV", "V", "vi", "vii"]
ROMAN_MINOR = ["i", "ii", "III", "iv", "v", "VI", "VII"]

# 风格族关键词（style_prompt 命中即归类；未命中默认 pop）
STYLE_KEYWORDS: dict[str, list[str]] = {
    "guofeng": ["国风", "古风", "民乐", "古筝", "笛子", "戏腔", "chinese"],
    "edm": ["edm", "电子舞曲", "舞曲", "house", "techno", "电音", "dance"],
    "hiphop": ["嘻哈", "hip", "hop", "说唱", "rap", "trap", "808"],
    "lofi": ["lo-fi", "lofi", "低保真", "chill", "爵士", "jazz", "咖啡馆"],
    "rock": ["摇滚", "rock", "乐队", "吉他摇滚", "失真"],
    "pop": ["流行", "pop", "民谣", "ballad", "抒情", "华语", "r&b", "rnb"],
}

# 和弦进行库：元素编码——0~6 = 调内音级索引；>=100 = 半音偏移（100+bVII→110）
PROGRESSIONS: dict[str, dict[str, list[list[int]]]] = {
    "pop": {
        "major": [[0, 4, 5, 3], [5, 3, 0, 4], [0, 5, 3, 4]],
        "minor": [[0, 5, 2, 6], [0, 3, 4, 0]],
    },
    "guofeng": {
        "major": [[0, 4, 5, 2], [3, 0, 4, 5]],
        "minor": [[0, 6, 5, 6], [0, 4, 5, 3]],
    },
    "edm": {
        "major": [[5, 3, 0, 4]],
        "minor": [[0, 5, 2, 6]],
    },
    "hiphop": {
        "major": [[0, 110], [0, 110]],
        "minor": [[0, 6], [0, 3]],
    },
    "lofi": {
        "major": [[1, 4, 0, 5]],
        "minor": [[0, 3, 6, 2]],
    },
    "rock": {
        "major": [[0, 3, 4], [0, 110, 3]],
        "minor": [[0, 110, 3], [0, 6, 3]],
    },
}


def detect_style_family(style_prompt: str) -> str:
    text = (style_prompt or "").lower()
    best, best_hits = "pop", 0
    for family, words in STYLE_KEYWORDS.items():
        hits = sum(1 for w in words if w in text)
        if hits > best_hits:
            best, best_hits = family, hits
    return best


def _chord_tones(root_pc: int, quality: str, colored: str | None) -> list[int]:
    if quality == "maj":
        tones = [root_pc, root_pc + 4, root_pc + 7]
        if colored == "sus4":
            tones = [root_pc, root_pc + 5, root_pc + 7]
    elif quality == "min":
        tones = [root_pc, root_pc + 3, root_pc + 7]
    else:  # dim
        tones = [root_pc, root_pc + 3, root_pc + 6]
    if colored == "add9":
        tones = tones + [root_pc + 14]
    return sorted({t % 12 for t in tones})


def _keyboard_voicing(tone_pcs: list[int], root_pc: int) -> list[int]:
    """键盘声部 voicing：和弦音放 C4(60)~B4(71) 区，根音就近放 C3~B3 区。"""
    mids = sorted({60 + (pc % 12) for pc in tone_pcs})
    root_low = 48 + (root_pc % 12)  # C3~B3
    return sorted(set(mids) | {root_low})


def build_harmony(ir: SongIR, rng: np.random.Generator) -> None:
    """逐段落选一条进行（seeded），段内循环填满小节；副歌 30% 概率加九音/挂留。"""
    req = ir.req
    ir.style_family = detect_style_family(req.style_prompt)
    family = ir.style_family
    scale = MAJOR_SCALE if req.mode == "major" else MINOR_SCALE
    triads = MAJOR_TRIADS if req.mode == "major" else MINOR_TRIADS
    romans = ROMAN_MAJOR if req.mode == "major" else ROMAN_MINOR
    tonic_pc = TONIC_PC[req.tonic]
    progs = PROGRESSIONS[family][req.mode]

    chords: list[ChordBar | None] = [None] * ir.total_bars
    for sp in ir.sections:
        prog = list(progs[int(rng.integers(0, len(progs)))])
        # hiphop 二和弦循环按 2 小节一格；其余每小节一格
        step = 2 if family == "hiphop" else 1
        for i in range(sp.bars):
            bar = sp.start_bar + i
            deg = prog[(i // step) % len(prog)]
            if deg >= 100:  # 半音偏移表示（rock/hiphop 的 bVII）
                offset = deg - 100
                root_pc = (tonic_pc + offset) % 12
                quality = "maj"
                roman = "bVII" if offset == 10 else f"+{offset}"
            else:
                offset = scale[deg]
                root_pc = (tonic_pc + offset) % 12
                quality = triads[deg]
                roman = romans[deg]
            colored = None
            if sp.section == "chorus" and rng.random() < 0.30:
                colored = "add9" if rng.random() < 0.5 else "sus4"
            tone_pcs = _chord_tones(root_pc, quality, colored)
            bass_midi = 33 + (root_pc % 12)  # A1~B2 低音区
            chords[bar] = ChordBar(
                bar=bar, root_pc=root_pc, roman=roman, tone_pcs=tone_pcs,
                bass_midi=bass_midi,
                key_midis=_keyboard_voicing(tone_pcs, root_pc),
            )
    ir.chords = [c for c in chords if c is not None]
