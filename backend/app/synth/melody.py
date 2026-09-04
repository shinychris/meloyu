"""阶段③：旋律生成（音节-音符对齐、调内约束、能量轮廓，架构 §7.5）。"""
from __future__ import annotations

import re

import numpy as np
from pypinyin import Style, pinyin

from app.synth.harmony import MAJOR_SCALE, MINOR_SCALE, TONIC_PC
from app.synth.ir import BAR_QUARTER_UNITS, Note, SongIR

# 人声类型的音域中心（MIDI）
VOCAL_CENTER = {
    "female_air": 72, "female_bright": 76, "female_deep": 65,
    "male_magnetic": 50, "male_clear": 57, "choir": 67, "instrumental": 67,
}
VOCAL_RANGE = 9  # ±半音

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uf900-\ufaff]")
_VOWELS = set("aeiouy")


def syllabify(line: str, language: str) -> list[str]:
    """音节切分：中文/日文逐字；英文按空格+元音组切分。"""
    syllables: list[str] = []
    if language in ("zh", "yue", "ja"):
        for ch in line:
            if _CJK_RE.match(ch) or ch.isalnum():
                syllables.append(ch)
        return syllables
    for word in re.findall(r"[A-Za-z']+", line):
        word = word.strip("'")
        if not word:
            continue
        cur = word[0]
        prev_vowel = word[0].lower() in _VOWELS
        for ch in word[1:]:
            is_vowel = ch.lower() in _VOWELS
            if is_vowel and not prev_vowel and len(cur) > 1:
                syllables.append(cur[:-1])
                cur = cur[-1]
            cur += ch
            prev_vowel = is_vowel
        if cur:
            syllables.append(cur)
    return syllables


def _scale_pcs(ir: SongIR) -> list[int]:
    scale = MAJOR_SCALE if ir.req.mode == "major" else MINOR_SCALE
    tonic = TONIC_PC[ir.req.tonic]
    return [(tonic + s) % 12 for s in scale]


def _chord_at(ir: SongIR, bar: int):
    for cb in ir.chords:
        if cb.bar == bar:
            return cb
    return ir.chords[-1] if ir.chords else None


def _pick_pitch(ir: SongIR, rng: np.random.Generator, chord, center: int,
                target: int, last_midi: int | None) -> int:
    """加权随机：和弦音 0.6 / 调内音 0.3 / 经过音 0.1；相邻音程 ≤ ±7。"""
    scale_pcs = _scale_pcs(ir)
    pool_chord = [m for m in range(max(40, center - 14), center + 15)
                  if m % 12 in chord.tone_pcs] if chord else []
    pool_scale = [m for m in range(max(40, center - 14), center + 15)
                  if m % 12 in scale_pcs]
    pool_passing = [m for m in range(max(40, center - 14), center + 15)]
    r = rng.random()
    if r < 0.6 and pool_chord:
        pool = pool_chord
    elif r < 0.9 and pool_scale:
        pool = pool_scale
    else:
        pool = pool_passing
    # 就近拱形目标 + 相邻音程限制
    def score(m: int) -> float:
        s = abs(m - target) * 1.0
        if last_midi is not None:
            s += max(0, abs(m - last_midi) - 7) * 4.0
        return s

    ranked = sorted(pool, key=score)
    # 目标附近加权抽取（前 6 候选按指数权重）
    top = ranked[:6]
    weights = np.array([1.6 ** (len(top) - 1 - i) for i in range(len(top))])
    weights = weights / weights.sum()
    return int(top[int(rng.choice(len(top), p=weights))])


def _compose_line(ir: SongIR, rng: np.random.Generator, start_bar: int, bars: int,
                  syllables: list[str], center: int, energy: float) -> list[Note]:
    """一个歌词行 → 一个乐句：拱形轮廓、句尾长音。"""
    beats_per_bar = BAR_QUARTER_UNITS[ir.req.time_signature]
    notes: list[Note] = []
    if not syllables:
        return notes
    n = len(syllables)
    total_beats = bars * beats_per_bar
    # 音符时长：八分为主，句尾长音（半小节以上）
    tail_beats = min(2.0, total_beats * 0.25)
    body_beats = total_beats - tail_beats
    if n == 1:
        durs = [total_beats]
    else:
        base = body_beats / (n - 1)
        durs = [base] * (n - 1) + [tail_beats]
    beat_cursor = 0.0  # 乐句内相对拍
    phrase_offset = start_bar * beats_per_bar  # 全曲绝对拍偏移
    last_midi: int | None = None
    for i, syl in enumerate(syllables):
        bar = start_bar + int(beat_cursor // beats_per_bar)
        chord = _chord_at(ir, min(bar, ir.total_bars - 1))
        # 拱形目标：起-扬-顶-收
        p = i / max(1, n - 1)
        arch = np.sin(np.pi * min(1.0, p * 1.15))  # 顶部略靠前
        target = int(round(center + arch * VOCAL_RANGE * (0.6 + 0.4 * energy)
                           - (0.35 * VOCAL_RANGE if p > 0.85 else 0)))
        midi = _pick_pitch(ir, rng, chord, center, target, last_midi)
        start_sec = (phrase_offset + beat_cursor) * (60.0 / ir.req.bpm)
        dur_sec = durs[i] * (60.0 / ir.req.bpm) * (0.92 if i < n - 1 else 1.0)
        vel = 0.55 + 0.35 * energy
        notes.append(Note(start=start_sec, dur=dur_sec, midi=midi, vel=vel, syllable=syl))
        last_midi = midi
        beat_cursor += durs[i]
    return notes


def _compose_instrumental_phrase(ir: SongIR, rng: np.random.Generator,
                                 start_bar: int, bars: int, energy: float) -> list[Note]:
    """纯器乐段：八分音符动机发展（动机 + 模进 + 收束长音）。"""
    beats_per_bar = BAR_QUARTER_UNITS[ir.req.time_signature]
    center = VOCAL_CENTER["instrumental"]
    scale_pcs = _scale_pcs(ir)
    total_beats = bars * beats_per_bar
    eighth = 0.5
    # 动机：2 小节的音程与节奏型
    motif_degrees = [int(rng.integers(0, 7)) for _ in range(4)]
    motif_rhythm = [eighth, eighth, eighth, eighth]  # 2 拍动机
    notes: list[Note] = []
    beat_cursor = 0.0  # 段内相对拍
    phrase_offset = start_bar * beats_per_bar  # 全曲绝对拍偏移
    mi = 0
    last_midi: int | None = None
    while beat_cursor < total_beats - 1e-6:
        remain = total_beats - beat_cursor
        if remain <= eighth * 2:  # 收束长音
            bar = start_bar + int(beat_cursor // beats_per_bar)
            chord = _chord_at(ir, min(bar, ir.total_bars - 1))
            target = center + 2
            midi = _pick_pitch(ir, rng, chord, center, target, last_midi)
            notes.append(Note(start=(phrase_offset + beat_cursor) * 60.0 / ir.req.bpm,
                              dur=remain * 60.0 / ir.req.bpm, midi=midi,
                              vel=0.5 + 0.3 * energy, syllable=""))
            break
        # 动机音高按调内级数模进
        deg = motif_degrees[mi % len(motif_degrees)]
        pc = scale_pcs[deg % 7]
        octave = center // 12 * 12
        midi = octave + pc
        while midi < center - 7:
            midi += 12
        while midi > center + 7:
            midi -= 12
        # 休止概率：低能量段稀疏
        if rng.random() > 0.25 * (1.2 - energy):
            notes.append(Note(start=(phrase_offset + beat_cursor) * 60.0 / ir.req.bpm,
                              dur=eighth * 0.9 * 60.0 / ir.req.bpm, midi=int(midi),
                              vel=0.45 + 0.3 * energy, syllable=""))
            last_midi = int(midi)
        beat_cursor += motif_rhythm[mi % len(motif_rhythm)]
        mi += 1
    return notes


def compose_melody(ir: SongIR, rng: np.random.Generator) -> None:
    """逐段落、逐行作曲；人声段落同步产出音节对齐的 vocal_notes。"""
    req = ir.req
    # FR-5：voice_clone 音域中心取档案实测基频（无档案参数时回退中性 60）
    if req.vocal == "voice_clone":
        center = int((req.voice_timbre or {}).get("center_midi", 60))
    else:
        center = VOCAL_CENTER[req.vocal]
    instrumental = req.vocal == "instrumental" or not req.lyrics
    for sp in ir.sections:
        if instrumental or not sp.lines:
            ir.melody += _compose_instrumental_phrase(ir, rng, sp.start_bar, sp.bars, sp.energy)
            continue
        # 行数与小节分配：每行至少 1 小节，长行 2 小节
        line_bars = max(1, sp.bars // max(1, len(sp.lines)))
        cursor = sp.start_bar
        end_bar = sp.start_bar + sp.bars
        for line in sp.lines:
            syls = syllabify(line, req.language)
            if not syls:
                continue
            bars = min(line_bars, end_bar - cursor)
            if bars <= 0:
                break
            phrase = _compose_line(ir, rng, cursor, bars, syls, center, sp.energy)
            ir.vocal_notes += phrase
            ir.melody += phrase  # 主旋律与人声旋律一致（音高线对齐）
            cursor += bars
        # 行分配剩余小节：器乐填充
        if cursor < end_bar:
            ir.melody += _compose_instrumental_phrase(ir, rng, cursor, end_bar - cursor,
                                                       sp.energy * 0.7)


def vowel_of_syllable(syl: str, language: str) -> str:
    """音节 → 主元音（共振峰查表键：a/i/u/e/o）。"""
    if language in ("zh", "yue", "ja") and _CJK_RE.match(syl):
        finals = pinyin(syl, style=Style.FINALS, strict=False)
        final = finals[0][0] if finals and finals[0] else ""
        return _main_vowel(final)
    for ch in reversed(syl.lower()):
        if ch in "aeiou":
            return "u" if ch in "u" else ch
    return "a"


def _main_vowel(final: str) -> str:
    """韵母 → 主元音：去介音(i/u/ü)、去鼻尾(n/ng)后取首元音。"""
    f = final.replace("ng", "n").replace("ü", "v")
    if len(f) > 1 and f[0] in "iuv" and f[1] in "aeiou":
        f = f[1:]
    f = f.replace("n", "")
    for ch in f:
        if ch in "aeiou":
            return ch
        if ch == "v":
            return "i"  # ü 近似 i 共振峰
    return "a"
