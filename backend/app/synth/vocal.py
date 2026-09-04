"""阶段⑤：合成人声（共振峰合成，vocoder/hum 风格——诚实定位见架构 §7.7）。

锯齿波源（加法合成限谐波）+ 两个共振峰带通（频域实现）+ 音高轨迹（颤音/滑音）
+ 音节包络 + 气声噪声。随机性全部来自传入的 seeded rng。
"""
from __future__ import annotations

import numpy as np

from app.synth.ir import SAMPLE_RATE, SongIR
from app.synth.melody import vowel_of_syllable

# 元音共振峰对 (F1, F2) Hz（架构 §7.7 查表）
FORMANTS: dict[str, tuple[float, float]] = {
    "a": (800.0, 1200.0),
    "i": (300.0, 2300.0),
    "u": (320.0, 800.0),
    "e": (400.0, 2100.0),
    "o": (500.0, 900.0),
}


def _midi_hz(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def _formant_response(n_fft: int, f1: float, f2: float) -> np.ndarray:
    """双共振峰频响（Lorentzian 峰，频域实现带通滤波）。"""
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / SAMPLE_RATE)
    b1, b2 = 90.0, 140.0
    h1 = 1.0 / (1.0 + ((freqs - f1) / (b1 * 0.5)) ** 2)
    h2 = 0.7 / (1.0 + ((freqs - f2) / (b2 * 0.5)) ** 2)
    return h1 + h2


def _syllable_wave(f0: float, dur: float, vowel: str, rng: np.random.Generator,
                   n_harm: int, detune_cents: float = 0.0,
                   prev_f0: float | None = None, formant_scale: tuple[float, float] = (1.0, 1.0)) -> np.ndarray:
    """合成一个音节：加法合成锯齿源 → 共振峰滤波 → 包络。"""
    n = max(8, int(dur * SAMPLE_RATE))
    t = np.arange(n) / SAMPLE_RATE
    f0_t = np.full(n, f0 * (2.0 ** (detune_cents / 1200.0)))
    # 音头滑音（40ms 从前一音 97% 滑入）
    glide_n = min(n, int(0.04 * SAMPLE_RATE))
    if glide_n > 1 and prev_f0:
        ramp = np.linspace(0.0, 1.0, glide_n)
        f0_t[:glide_n] = prev_f0 + (f0_t[:glide_n] - prev_f0) * ramp ** 0.7
    # 5Hz 颤音（150ms 渐入，深度 ±0.6%）
    vib_n = min(n, int(0.15 * SAMPLE_RATE))
    vib_env = np.ones(n)
    if vib_n > 1:
        vib_env[:vib_n] = np.linspace(0, 1, vib_n)
    f0_t = f0_t * (1.0 + 0.006 * vib_env * np.sin(2 * np.pi * 5.0 * t))

    phase = 2.0 * np.pi * np.cumsum(f0_t) / SAMPLE_RATE
    f_max = float(np.max(f0_t))
    k_max = max(2, min(n_harm, int((SAMPLE_RATE * 0.42) / max(40.0, f_max))))
    ks = np.arange(1, k_max + 1, dtype=np.float64)
    amps = (1.0 / ks ** 0.9) * np.exp(-ks * f_max / 9000.0)
    src = np.sin(np.outer(ks, phase) * 1.0)
    wave = (amps @ src) / max(1.0, float(amps.sum())) * 1.8

    # 共振峰滤波（频域）
    n_fft = 1 << max(9, int(np.ceil(np.log2(n))))
    spec = np.fft.rfft(wave, n=n_fft)
    f1, f2 = FORMANTS.get(vowel, FORMANTS["a"])
    # FR-5：voice_clone 按档案实测共振峰比例缩放（参数级适配，非采样）
    spec *= _formant_response(n_fft, f1 * formant_scale[0], f2 * formant_scale[1])
    wave = np.fft.irfft(spec, n=n_fft)[:n]

    # 包络：20ms 起音 / 90ms 收尾 / 轻微衰减
    atk = min(n // 2, int(0.02 * SAMPLE_RATE))
    rel = min(n // 2, int(0.09 * SAMPLE_RATE))
    env = np.ones(n)
    if atk > 0:
        env[:atk] = np.linspace(0.0, 1.0, atk) ** 0.8
    if rel > 0:
        env[-rel:] *= np.linspace(1.0, 0.0, rel) ** 1.2
    env *= 1.0 - 0.15 * t / max(dur, 1e-6)
    wave *= env

    # 气声：白噪声 −18dB 叠加
    noise = rng.standard_normal(n) * 0.126 * env
    return wave + noise


def synth_vocal(ir: SongIR, rng: np.random.Generator, bus: np.ndarray) -> None:
    """把人声旋律写入 bus（mono float64，与鼓/贝斯同一采样网格）。"""
    req = ir.req
    if req.vocal == "instrumental" or not ir.vocal_notes:
        return
    n_harm = 28 if req.model == "v1_pro" else 16
    # FR-5：voice_clone 谐波数按档案亮度系数调整（限 12~40）
    timbre = req.voice_timbre or {}
    formant_scale = (float(timbre.get("f1_scale", 1.0)), float(timbre.get("f2_scale", 1.0)))
    if timbre.get("harm_scale"):
        n_harm = int(max(12, min(40, round(n_harm * float(timbre["harm_scale"])))))
    prev_f0: float | None = None
    for note in ir.vocal_notes:
        vowel = vowel_of_syllable(note.syllable, req.language)
        f0 = _midi_hz(note.midi)
        copies = 1
        detunes = [0.0]
        if req.vocal == "choir":
            copies, detunes = 3, [-8.0, 0.0, 8.0]
        seg_total = np.zeros(max(8, int(note.dur * SAMPLE_RATE)))
        for dc in detunes:
            seg = _syllable_wave(f0, note.dur, vowel, rng, n_harm, dc, prev_f0, formant_scale)
            seg_total[:len(seg)] += seg
        seg_total /= copies
        seg_total *= note.vel * 0.9
        i0 = int(note.start * SAMPLE_RATE)
        i1 = min(len(bus), i0 + len(seg_total))
        if i1 > i0:
            bus[i0:i1] += seg_total[: i1 - i0]
        prev_f0 = f0
