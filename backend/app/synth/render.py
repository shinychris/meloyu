"""阶段⑥⑦：混音与分轨渲染。

- 四总线 vocals/drums/bass/other 在同一采样网格分别求和 → stems 相位对齐由构造保证。
- 简单混响（指数衰减噪声 IR，FFT overlap-add 卷积，仅 vocal/other，12% 湿声）。
- 软限幅（tanh）+ RMS 响度归一（简化，非严格 BS.1770）。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.synth.ir import SAMPLE_RATE, SongIR
from app.synth.vocal import synth_vocal

REVERB_SEC = 1.6
REVERB_WET = 0.12


@dataclass
class RenderResult:
    master_l: np.ndarray
    master_r: np.ndarray
    stems: dict[str, np.ndarray]


def _midi_hz(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


# ---- 乐器音色（other / bass 总线）----

def _piano_note(midi: int, dur: float, vel: float, rng: np.random.Generator,
                n_harm: int = 6) -> np.ndarray:
    """电钢琴质感：加法合成 + 指数衰减 + 双失谐层。"""
    n = max(8, int(dur * SAMPLE_RATE))
    t = np.arange(n) / SAMPLE_RATE
    f0 = _midi_hz(midi)
    k_max = max(2, min(n_harm, int((SAMPLE_RATE * 0.45) / f0)))
    ks = np.arange(1, k_max + 1, dtype=np.float64)
    amps = (1.0 / ks ** 1.1)
    phase1 = 2 * np.pi * f0 * t
    phase2 = 2 * np.pi * f0 * 1.0015 * t
    src = np.sin(np.outer(ks, phase1)) + 0.5 * np.sin(np.outer(ks, phase2))
    wave = amps @ src
    wave /= max(1.0, float(np.abs(wave).max()) + 1e-9)
    # 衰减：高音衰减快
    tau = max(0.4, 3.2 - (midi - 36) * 0.028)
    env = np.exp(-t / tau)
    atk = min(n // 3, int(0.004 * SAMPLE_RATE))
    if atk > 0:
        env[:atk] *= np.linspace(0, 1, atk)
    return wave * env * vel * 0.5


def _pad_note(midi: int, dur: float, vel: float) -> np.ndarray:
    """弦乐铺底：锯齿限谐波 + 低通（频域）+ 慢起音。"""
    n = max(8, int(dur * SAMPLE_RATE))
    t = np.arange(n) / SAMPLE_RATE
    f0 = _midi_hz(midi)
    k_max = max(2, min(10, int(1800.0 / f0)))
    ks = np.arange(1, k_max + 1, dtype=np.float64)
    wave = (1.0 / ks ** 1.2) @ np.sin(np.outer(ks, 2 * np.pi * f0 * t))
    n_fft = 1 << max(9, int(np.ceil(np.log2(n))))
    spec = np.fft.rfft(wave, n=n_fft)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / SAMPLE_RATE)
    lp = 1.0 / (1.0 + (freqs / 1800.0) ** 4)
    wave = np.fft.irfft(spec * lp, n=n_fft)[:n]
    atk = min(n // 2, int(0.35 * SAMPLE_RATE))
    rel = min(n // 2, int(0.5 * SAMPLE_RATE))
    env = np.ones(n)
    if atk > 0:
        env[:atk] = np.linspace(0, 1, atk) ** 2
    if rel > 0:
        env[-rel:] *= np.linspace(1, 0, rel) ** 1.5
    return wave * env * vel * 0.32


def _bass_note(midi: int, dur: float, vel: float, family: str) -> np.ndarray:
    """贝斯：正弦基频 + 少量二次谐波 + 软饱和；hiphop 808 加滑音。"""
    n = max(8, int(dur * SAMPLE_RATE))
    t = np.arange(n) / SAMPLE_RATE
    f0 = _midi_hz(midi)
    if family == "hiphop":  # 808 起音略高滑落
        f_t = f0 * (1.0 + 0.25 * np.exp(-t / 0.06))
        phase = 2 * np.pi * np.cumsum(f_t) / SAMPLE_RATE
        wave = np.sin(phase) + 0.18 * np.sin(2 * phase)
    else:
        wave = np.sin(2 * np.pi * f0 * t) + 0.22 * np.sin(4 * np.pi * f0 * t)
    wave = np.tanh(wave * 1.6) * 0.7
    atk = min(n // 2, int(0.008 * SAMPLE_RATE))
    rel = min(n // 2, int(0.05 * SAMPLE_RATE))
    env = np.ones(n)
    if atk > 0:
        env[:atk] = np.linspace(0, 1, atk)
    if rel > 0:
        env[-rel:] *= np.linspace(1, 0, rel)
    return wave * env * vel * 0.62


# ---- 鼓组（噪声+正弦合成打击乐）----

def _kick(vel: float) -> np.ndarray:
    n = int(0.28 * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    f = 45.0 + 115.0 * np.exp(-t / 0.03)
    phase = 2 * np.pi * np.cumsum(f) / SAMPLE_RATE
    env = np.exp(-t / 0.11)
    click = 0.25 * np.exp(-t / 0.002) * np.sin(2 * np.pi * 1200 * t)
    return (np.sin(phase) + click) * env * vel * 0.95


def _snare(vel: float, rng: np.random.Generator) -> np.ndarray:
    n = int(0.16 * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    noise = rng.standard_normal(n)
    noise = np.diff(noise, prepend=0.0)  # 高通近似
    tone = np.sin(2 * np.pi * 190.0 * t) * np.exp(-t / 0.04)
    env = np.exp(-t / 0.055)
    return (noise * env * 0.55 + tone * 0.45) * vel * 0.7


def _hat(vel: float, rng: np.random.Generator, open_hat: bool = False) -> np.ndarray:
    dur = 0.09 if open_hat else 0.035
    n = int(dur * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    noise = rng.standard_normal(n)
    noise = np.diff(np.diff(noise, prepend=0.0), prepend=0.0)  # 二阶差分提亮
    env = np.exp(-t / (0.06 if open_hat else 0.012))
    return noise * env * vel * 0.28


# ---- 混响（FFT overlap-add 卷积，避免整段大 FFT 内存峰值）----

def _reverb_ir(rng: np.random.Generator) -> np.ndarray:
    """指数衰减白噪声 IR，单位 L2 范数（湿声幅度由 REVERB_WET 控制）。"""
    n = int(REVERB_SEC * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    ir = rng.standard_normal(n) * np.exp(-t / 0.38)
    return ir / (np.sqrt(np.sum(ir * ir)) + 1e-12)


def _fft_convolve(dry: np.ndarray, ir: np.ndarray) -> np.ndarray:
    n_out = len(dry) + len(ir) - 1
    block = 1 << max(10, int(np.ceil(np.log2(len(ir) * 4))))
    ir_spec = np.fft.rfft(ir, n=block)
    out = np.zeros(n_out)
    for start in range(0, len(dry), block - len(ir) + 1):
        seg_len = min(block - len(ir) + 1, len(dry) - start)
        seg = dry[start: start + seg_len]
        conv = np.fft.irfft(np.fft.rfft(seg, n=block) * ir_spec, n=block)
        out[start: start + min(block, n_out - start)] += conv[: min(block, n_out - start)]
    return out[: len(dry)]


def render_song(ir: SongIR, rng: np.random.Generator) -> RenderResult:
    """阶段⑥⑦：各声部渲染 → 四总线 → 混响 → 母带。"""
    total = int(round(ir.total_sec * SAMPLE_RATE))
    total = max(total, SAMPLE_RATE)
    buses = {
        "vocals": np.zeros(total),
        "drums": np.zeros(total),
        "bass": np.zeros(total),
        "other": np.zeros(total),
    }
    quality = 1.0 if ir.req.model == "v1_pro" else 0.6

    # 人声
    synth_vocal(ir, rng, buses["vocals"])

    # 鼓
    for hit in ir.drums:
        if hit.kind == "kick":
            seg = _kick(hit.vel)
        elif hit.kind == "snare":
            seg = _snare(hit.vel, rng)
        else:
            seg = _hat(hit.vel, rng, hit.kind == "open_hat")
        i0 = int(hit.start * SAMPLE_RATE)
        i1 = min(total, i0 + len(seg))
        if i1 > i0:
            buses["drums"][i0:i1] += seg[: i1 - i0]

    # 贝斯
    for note in ir.bass_notes:
        seg = _bass_note(note.midi, note.dur, note.vel, ir.style_family)
        i0 = int(note.start * SAMPLE_RATE)
        i1 = min(total, i0 + len(seg))
        if i1 > i0:
            buses["bass"][i0:i1] += seg[: i1 - i0]

    # other 总线：钢琴（和弦节奏）+ 弦乐 pad（副歌/桥段）+ 主旋律倍频层
    beats_per_bar = {"4/4": 4.0, "3/4": 3.0, "6/8": 3.0}[ir.req.time_signature]
    beat = 60.0 / ir.req.bpm
    for sp in ir.sections:
        pad_on = sp.section in ("chorus", "bridge", "pre_chorus", "post_chorus",
                                "drop") and sp.energy >= 0.4
        for b in range(sp.bars):
            bar = sp.start_bar + b
            if bar >= len(ir.chords):
                break
            cb = ir.chords[bar]
            bar_start = bar * beats_per_bar * beat
            # 钢琴：低能量/叙事段分解和弦（根-五-三-八度琶音），高能量段柱式
            if (sp.section in ("verse", "intro", "outro", "spoken", "interlude",
                               "breakdown", "ad_lib") or ir.req.vocal == "instrumental"):
                seq = [0, 4, 2, 3] if beats_per_bar >= 4 else [0, 2, 3]
                for si, beat_pos in enumerate(seq):
                    if beat_pos >= beats_per_bar:
                        continue
                    if rng.random() > 0.55 + 0.4 * sp.energy:
                        continue
                    idx = si % len(cb.key_midis)
                    midi = cb.key_midis[idx] + 12 if sp.energy < 0.5 else cb.key_midis[idx]
                    seg = _piano_note(midi, beat * 1.8, 0.5 + 0.3 * sp.energy, rng)
                    i0 = int((bar_start + beat_pos * beat) * SAMPLE_RATE)
                    i1 = min(total, i0 + len(seg))
                    if i1 > i0:
                        buses["other"][i0:i1] += seg[: i1 - i0] * (0.8 + 0.2 * quality)
            else:
                # 柱式和弦（每拍或半小节）
                hits_at = [0.0, beats_per_bar / 2] if beats_per_bar >= 4 else [0.0]
                for hp in hits_at:
                    for midi in cb.key_midis:
                        seg = _piano_note(midi, beat * 1.2, 0.42 + 0.25 * sp.energy, rng)
                        i0 = int((bar_start + hp * beat) * SAMPLE_RATE)
                        i1 = min(total, i0 + len(seg))
                        if i1 > i0:
                            buses["other"][i0:i1] += seg[: i1 - i0] * (0.8 + 0.2 * quality)
            # 弦乐 pad：整小节
            if pad_on:
                for midi in cb.key_midis[:3]:
                    seg = _pad_note(midi + 12, beats_per_bar * beat, 0.5 + 0.3 * sp.energy)
                    i0 = int(bar_start * SAMPLE_RATE)
                    i1 = min(total, i0 + len(seg))
                    if i1 > i0:
                        buses["other"][i0:i1] += seg[: i1 - i0]

    # 器乐主旋律层（instrumental 或叠加八度亮化层）
    if ir.req.vocal == "instrumental":
        for note in ir.melody:
            seg = _piano_note(note.midi, note.dur, note.vel, rng, n_harm=7)
            i0 = int(note.start * SAMPLE_RATE)
            i1 = min(total, i0 + len(seg))
            if i1 > i0:
                buses["other"][i0:i1] += seg[: i1 - i0] * 1.15

    # 尾奏淡出
    fade = int(min(3.0, ir.total_sec * 0.08) * SAMPLE_RATE)
    if fade > 0 and total > fade:
        env = np.ones(total)
        env[-fade:] = np.linspace(1.0, 0.0, fade)
        for k in buses:
            buses[k] *= env

    # 混响（仅 vocals / other，12% 湿声）
    ir_audio = _reverb_ir(rng)
    for k in ("vocals", "other"):
        wet = _fft_convolve(buses[k], ir_audio)
        buses[k] = buses[k] + wet * REVERB_WET

    # 母带：总线求和 + 轻声像展宽 + 软限幅 + RMS 归一
    mid = buses["vocals"] + buses["drums"] + buses["bass"] + buses["other"]
    delay_n = int(0.0035 * SAMPLE_RATE)  # 3.5ms 哈斯效应对 other 展宽
    wide = np.zeros_like(buses["other"])
    wide[delay_n:] = buses["other"][:-delay_n] if delay_n > 0 else buses["other"]
    master_l = mid + 0.18 * wide
    master_r = mid - 0.18 * wide

    for _side, sig in (("L", master_l), ("R", master_r)):
        peak = float(np.max(np.abs(sig))) if len(sig) else 0.0
        if peak > 0.98:  # 软限幅
            sig[:] = np.tanh(sig / peak * 1.2) / np.tanh(1.2)
    # RMS 响度归一（简化，非严格 BS.1770）：目标 -16 dBFS，峰值护栏 0.98
    both = np.concatenate([master_l, master_r]) if len(master_l) else master_l
    rms = float(np.sqrt(np.mean(both * both))) if len(both) else 0.0
    if rms > 1e-9:
        gain = 0.158 / rms
        peak_after = max(float(np.max(np.abs(master_l))), float(np.max(np.abs(master_r))))
        if peak_after * gain > 0.97:
            gain = 0.97 / max(peak_after, 1e-9)
        master_l = master_l * gain
        master_r = master_r * gain
        stems = {k: (v * gain) for k, v in buses.items()}
        # stems 同步限幅防削波
        for k, v in stems.items():
            p = float(np.max(np.abs(v)))
            if p > 0.98:
                stems[k] = np.tanh(v / p * 1.2) / np.tanh(1.2)
    else:
        stems = dict(buses)

    return RenderResult(master_l=master_l, master_r=master_r, stems=stems)
