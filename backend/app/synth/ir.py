"""合成管线中间表示（SongIR）：阶段间禁止直传 ndarray，保证每阶段可单测。"""
from __future__ import annotations

from dataclasses import dataclass, field

SAMPLE_RATE = 48000

# 拍号 → 每小节四分音符单位数（6/8 = 6 个八分音符 = 3 个四分单位）
BAR_QUARTER_UNITS = {"4/4": 4.0, "3/4": 3.0, "6/8": 3.0}
# 每小节细分子拍数（16 分网格，6/8 以 8 分为最小格 → 12 格）
BAR_SUBDIV = {"4/4": 16, "3/4": 12, "6/8": 12}


@dataclass
class Note:
    """单音符事件（旋律/贝斯/和声声部通用）。"""
    start: float          # 秒（相对全曲 0 点）
    dur: float            # 秒
    midi: int             # MIDI 音号
    vel: float            # 0~1 力度
    syllable: str = ""    # 人声音节（仅人声旋律）


@dataclass
class DrumHit:
    start: float
    kind: str   # kick / snare / hat / open_hat
    vel: float


@dataclass
class ChordBar:
    """一个小节的和声：根音 pitch-class、三和弦音（可含九音/挂留扩展）。"""
    bar: int
    root_pc: int
    roman: str            # 级数显示（I / vi / bVII…）
    tone_pcs: list[int]   # 和弦音 pitch-class
    bass_midi: int        # 贝斯根音 MIDI（低音区）
    key_midis: list[int]  # 键盘声部 voicing（中音区）


@dataclass
class SectionPlan:
    section: str          # intro/verse/pre_chorus/chorus/bridge/outro
    start_bar: int
    bars: int
    energy: float
    lines: list[str] = field(default_factory=list)


@dataclass
class SongRequest:
    """LocalSynthProvider 的输入（由 services.generation 组装）。"""
    style_prompt: str
    negative_prompt: str
    model: str                     # v1_pro / v1_fast
    lyrics: str
    bpm: int
    tonic: str                     # C..B
    mode: str                      # major / minor
    time_signature: str
    duration_sec: int
    vocal: str
    language: str
    instrument_density: int
    seed: int
    # FR-5（v0.8.2）：voice_clone 的音色参数（音域中心/共振峰缩放/谐波系数）
    voice_timbre: dict | None = None


@dataclass
class SongIR:
    """八阶段管线在内存中的统一表示。"""
    req: SongRequest
    seed: int
    inferred_structure: bool = False
    style_family: str = "pop"
    total_bars: int = 0
    bar_sec: float = 0.0
    sections: list[SectionPlan] = field(default_factory=list)
    chords: list[ChordBar] = field(default_factory=list)          # 按 bar 索引对齐
    melody: list[Note] = field(default_factory=list)              # 器乐主旋律（含 instrumental 主奏）
    vocal_notes: list[Note] = field(default_factory=list)         # 人声旋律（音节对齐）
    bass_notes: list[Note] = field(default_factory=list)
    drums: list[DrumHit] = field(default_factory=list)
    applied_negative: list[str] = field(default_factory=list)

    @property
    def total_sec(self) -> float:
        return self.total_bars * self.bar_sec

    def structure_json(self) -> list[dict]:
        out = []
        for sp in self.sections:
            out.append({
                "section": sp.section,
                "bars": sp.bars,
                "start_bar": sp.start_bar,
                "start_sec": round(sp.start_bar * self.bar_sec, 2),
                "end_sec": round((sp.start_bar + sp.bars) * self.bar_sec, 2),
            })
        return out
