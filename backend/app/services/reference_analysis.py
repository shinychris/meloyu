"""参考音频特征分析（FR-4）：BPM / 调性 / 能量 / 亮度（numpy，无新依赖）。

分析对象为 wav（浏览器 AudioContext 解码重采样的渲染，或 wav 原件）。
口径：特征级参考（非采样）——输出仅参数化特征，不保留旋律波形。
"""
from __future__ import annotations

import wave as wav_mod
from pathlib import Path

import numpy as np

# Krumhansl-Kessler 调性轮廓（大/小调各 12 半音，从主音起）
_KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_PC_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    """wav → mono float64 [-1,1]（任意声道/位深 16/24/32）。"""
    with wav_mod.open(str(path), "rb") as wf:
        n, ch, sw, sr = wf.getnframes(), wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
        raw = wf.readframes(n)
    if sw == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        data = v.astype(np.float64) / float(1 << 23)
    else:
        dt = "<i2" if sw == 2 else "<i4"
        data = np.frombuffer(raw, dtype=dt).astype(np.float64) / float(1 << (8 * sw - 1))
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


def detect_bpm(x: np.ndarray, sr: int, lo: int = 60, hi: int = 174) -> int:
    """谱通量 onset + 自相关估 BPM。

    谱通量（半波整流谱差）对调性垫乐的调幅干扰远比能量包络稳健；
    倍频歧义（半/倍速）用对数节拍先验（中心 ~120BPM）在 ≥95% 最高分的
    近分候选中裁决。结果为**估计值**（±1 倍频程歧义为自相关类算法固有），
    前端展示后用户可改——参考的语义是参数建议而非强制。
    """
    win, hop = 1024, 256
    n_frames = max(2, (len(x) - win) // hop)
    idx = np.arange(n_frames) * hop
    frames = np.stack([x[i:i + win] for i in idx])
    spec = np.abs(np.fft.rfft(frames * np.hanning(win), axis=1))
    flux = np.maximum(np.diff(spec, axis=0).sum(axis=1), 0.0)
    if flux.std() < 1e-9:
        return 90  # 静音/恒定信号：无节奏信息，回退默认
    onset = (flux - flux.mean()) / (flux.std() + 1e-12)
    fps = sr / hop
    ac = np.correlate(onset, onset, mode="full")[len(onset) - 1:]

    def ac_at(lag: float) -> float:
        """分数 lag 的线性插值自相关值。"""
        i = int(lag)
        if i < 0 or i + 1 >= len(ac):
            return -np.inf
        frac = lag - i
        return float(ac[i] * (1 - frac) + ac[i + 1] * frac)

    # 纯主峰打分 + 节拍先验：自相关在 n×拍周期处同样出峰（半/倍速歧义），
    # 对近分候选（≥95% 最高分）取对数节拍先验（中心 ~120BPM）最接近者
    scored: list[tuple[float, float]] = []
    for bpm in np.arange(lo, hi + 0.5, 0.5):
        lag = fps * 60.0 / bpm
        if lag < 2 or lag >= len(ac) - 1:
            continue
        scored.append((ac_at(lag), float(bpm)))
    if not scored:
        return 90
    top = max(s for s, _ in scored)
    prior_center = 120.0
    best = min((b for s, b in scored if s >= 0.95 * top),
               key=lambda b: abs(np.log(b / prior_center)), default=90.0)
    return int(round(best))


def detect_key(x: np.ndarray, sr: int) -> tuple[str, str]:
    """色度向量 × Krumhansl 轮廓相关 → (tonic, mode)。"""
    n = 1 << 15  # 32k FFT @ 常见采样率 ≈ 1.5Hz 分辨率
    usable = len(x) - len(x) % n
    if usable < n:
        return "A", "minor"
    blocks = x[:usable].reshape(-1, n)
    spec = np.abs(np.fft.rfft(blocks, axis=1))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    chroma = np.zeros(12)
    mask = (freqs >= 55) & (freqs <= 2000)  # A1..~B6 有效乐音区
    if mask.any():
        mags = spec[:, mask]
        pcs = (np.round(12 * np.log2(freqs[mask] / 440.0)).astype(int) + 9) % 12
        for pc in range(12):
            chroma[pc] = mags[:, pcs == pc].sum()
    if chroma.sum() <= 0:
        return "A", "minor"
    chroma = chroma / chroma.sum()

    def corr(a: np.ndarray, b: np.ndarray) -> float:
        a = a - a.mean()
        b = b - b.mean()
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

    best = (-2.0, "A", "minor")
    for tonic in range(12):
        rotated = np.roll(chroma, -tonic)
        c_maj = corr(rotated, _KK_MAJOR)
        c_min = corr(rotated, _KK_MINOR)
        if c_maj > best[0]:
            best = (c_maj, _PC_NAMES[tonic], "major")
        if c_min > best[0]:
            best = (c_min, _PC_NAMES[tonic], "minor")
    return best[1], best[2]


def analyze_wav(path: Path) -> dict:
    """入口：wav → {bpm, key, energy, brightness, duration_sec}。"""
    x, sr = read_wav_mono(path)
    duration = len(x) / sr
    if len(x) == 0:
        raise ValueError("empty wav")
    rms = float(np.sqrt(np.mean(x ** 2)))
    # 亮度：全段谱质心占比（0=沉闷低频，1=明亮高频）
    n = 1 << 14
    usable = len(x) - len(x) % n
    blocks = x[:usable].reshape(-1, n)
    spec = np.abs(np.fft.rfft(blocks, axis=1)).mean(axis=0)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    centroid = float((freqs * spec).sum() / (spec.sum() + 1e-12))
    brightness = max(0.0, min(1.0, centroid / (sr / 4)))  # 以 sr/4 为 1.0 锚点
    energy = max(0.05, min(1.0, rms / 0.25))
    tonic, mode = detect_key(x, sr)
    return {
        "bpm": detect_bpm(x, sr),
        "key_tonic": tonic,
        "key_mode": mode,
        "energy": round(energy, 3),
        "brightness": round(brightness, 3),
        "duration_sec": round(duration, 1),
    }
