"""哼唱成歌（v0.11.0）：录音波形 → 音高轮廓（f0 自相关 + 音符分割）。

管线（全部真实信号处理，无占位）：
1. wav 解码（PCM16/24/float32，单声道混合，任意采样率 8k~48k）；
2. 逐帧 f0：40ms 窗 / 10ms hop，带 RMS 静音门限，归一化自相关峰 + 抛物线插值，
   搜索 80~1000Hz（覆盖人声哼唱域）；
3. 帧序列 → 音符分割：连续相近 f0（±0.8 半音）聚为一个音符，最短 90ms；
4. 半音序列相对自身中位音（生成端再按音域适配，这里只报相对音高）；
5. bpm 提示：音符起点间隔中位数 → 折算拍速（仅展示参考，不强制）。

用法：POST /api/v1/hum/analyze（octet-stream wav ≤8MB ≤60s）。
"""
from __future__ import annotations

import io
import wave as wav_mod

import numpy as np

from app.core.errors import err_validation
from app.core.i18n import tr

MAX_HUM_BYTES = 8 * 1024 * 1024
MAX_HUM_SEC = 60.0
F0_MIN_HZ, F0_MAX_HZ = 80.0, 1000.0
FRAME_SEC, HOP_SEC = 0.04, 0.01
MIN_NOTE_SEC = 0.09
RMS_GATE_RATIO = 0.08   # 相对全曲峰值 RMS 的静音门限
SEMI_TOL = 0.8          # 帧间聚合容差（半音）


def _decode_wav(raw: bytes) -> tuple[np.ndarray, int]:
    """wav 字节 → (mono float64 [-1,1], sample_rate)。"""
    try:
        with wav_mod.open(io.BytesIO(raw), "rb") as wf:
            n, ch, sw, sr = (wf.getnframes(), wf.getnchannels(),
                             wf.getsampwidth(), wf.getframerate())
            if sw == 1:
                data = np.frombuffer(wf.readframes(n), dtype=np.uint8)
                x = (data.astype(np.float64) - 128.0) / 128.0
            elif sw == 2:
                data = np.frombuffer(wf.readframes(n), dtype="<i2")
                x = data.astype(np.float64) / 32768.0
            elif sw == 3:
                b = np.frombuffer(wf.readframes(n), dtype=np.uint8).reshape(-1, 3)
                v = b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16)
                v = np.where(v >= (1 << 23), v - (1 << 24), v)  # 符号扩展
                x = v.astype(np.float64) / float(1 << 23)
            elif sw == 4:
                data = np.frombuffer(wf.readframes(n), dtype="<f4")
                x = data.astype(np.float64)
            else:
                raise ValueError
            if ch > 1:
                x = x.reshape(-1, ch).mean(axis=1)
            return x, int(sr)
    except Exception as e:
        raise err_validation(tr("哼唱音频须为 WAV（PCM 16/24bit 或 float32）",
                            "Hum audio must be WAV (PCM 16/24-bit or float32)")) from e


def _frame_f0(x: np.ndarray, sr: int, rms_peak: float) -> tuple[np.ndarray, np.ndarray]:
    """逐帧 f0（Hz；无决策 None=nan）与帧 RMS。归一化自相关 + 抛物线插值。"""
    win = max(64, int(FRAME_SEC * sr)) & ~1
    hop = max(8, int(HOP_SEC * sr))
    lag_min = int(sr / F0_MAX_HZ)
    lag_max = min(int(sr / F0_MIN_HZ), win // 2)
    frames = range(0, max(0, len(x) - win), hop)
    f0 = np.full(len(frames) or 1, np.nan)
    rms = np.zeros(len(frames) or 1)
    gate = rms_peak * RMS_GATE_RATIO
    for i, start in enumerate(frames):
        seg = x[start:start + win]
        rms[i] = float(np.sqrt(np.mean(seg * seg)))
        if rms[i] < gate:
            continue
        seg = seg - seg.mean()
        energy = float(np.sum(seg * seg))
        if energy < 1e-9:
            continue
        ac = np.correlate(seg, seg, mode="full")[win - 1:]
        ac = ac / ac[0] if ac[0] > 0 else ac
        seg_lag = ac[lag_min:lag_max + 1]
        if len(seg_lag) < 3:
            continue
        k = int(np.argmax(seg_lag))
        if seg_lag[k] < 0.45:  # 峰显著性门限
            continue
        # 抛物线插值细化 lag
        if 0 < k < len(seg_lag) - 1:
            a, b, c = seg_lag[k - 1], seg_lag[k], seg_lag[k + 1]
            denom = a - 2 * b + c
            delta = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
            lag = lag_min + k + float(np.clip(delta, -1.0, 1.0))
        else:
            lag = lag_min + k
        f0[i] = sr / lag
    return f0, rms


def _split_notes(f0: np.ndarray, rms: np.ndarray, hop_sec: float,
                 rms_peak: float) -> list[dict]:
    """帧 f0 → 音符段（连续 ±SEMI_TOL 半音聚合；静音为断点）。"""
    notes: list[dict] = []
    cur: dict | None = None
    gate = rms_peak * RMS_GATE_RATIO
    for i in range(len(f0)):
        hz = f0[i]
        if np.isnan(hz) or rms[i] < gate:
            cur = None
            continue
        semi = 12.0 * np.log2(hz / 440.0) + 69.0  # MIDI 实数
        if cur is not None and abs(semi - cur["semi_sum"] / cur["n"]) <= SEMI_TOL:
            cur["semi_sum"] += semi
            cur["n"] += 1
            cur["end"] = (i + 1) * hop_sec
        else:
            if cur is not None and cur["end"] - cur["start"] >= MIN_NOTE_SEC:
                notes.append(cur)
            cur = {"semi_sum": semi, "n": 1, "start": i * hop_sec,
                   "end": (i + 1) * hop_sec, "conf": 0.0}
    if cur is not None and cur["end"] - cur["start"] >= MIN_NOTE_SEC:
        notes.append(cur)
    return notes


def analyze_hum(raw: bytes) -> dict:
    """wav 字节 → 音高轮廓（相对半音序列 + 时长拍长 + bpm 提示 + 置信度）。"""
    if len(raw) > MAX_HUM_BYTES:
        raise err_validation(tr(f"哼唱音频超过 {MAX_HUM_BYTES // 1024 // 1024}MB 上限",
                            f"Hum audio exceeds the {MAX_HUM_BYTES // 1024 // 1024}MB limit"))
    x, sr = _decode_wav(raw)
    dur = len(x) / sr
    if dur < 1.0:
        raise err_validation(tr("哼唱太短（至少 1 秒）", "Humming too short (at least 1 second)"))
    if dur > MAX_HUM_SEC:
        raise err_validation(tr(f"哼唱超过 {MAX_HUM_SEC:.0f}s 上限",
                            f"Humming exceeds the {MAX_HUM_SEC:.0f}s limit"))

    # 预扫峰值 RMS 供静音门限
    win = max(64, int(FRAME_SEC * sr)) & ~1
    frames = np.lib.stride_tricks.sliding_window_view(x, win)[::max(8, win // 4)]
    rms_peak = float(np.sqrt((frames ** 2).mean(axis=1).max())) if len(frames) else 0.0
    if rms_peak < 1e-4:
        raise err_validation(tr("未检测到有效声音（请靠近麦克风重新哼唱）",
                            "No audible signal detected (hum again closer to the mic)"))

    f0, rms = _frame_f0(x, sr, rms_peak)
    hop_sec = max(8, int(HOP_SEC * sr)) / sr
    voiced = float(np.mean(~np.isnan(f0)))
    if voiced < 0.15:
        raise err_validation(tr("音高信号太弱（请用『啊——』或『嘟——』平稳哼唱旋律）",
                            "Pitch signal too weak (hum steadily with 'ahh' or 'doo')"))

    notes = _split_notes(f0, rms, hop_sec, rms_peak)
    if len(notes) < 2:
        raise err_validation(tr("至少需要 2 个可辨识音符", "At least 2 identifiable notes are required"))
    midis = [n["semi_sum"] / n["n"] for n in notes]
    med = sorted(midis)[len(midis) // 2]
    semis = [round(m - med) for m in midis]

    # bpm 提示：音符起点间隔中位数 ≈ 半拍/一拍假设下取 [60,174] 内最近值
    starts = [n["start"] for n in notes]
    gaps = [b - a for a, b in zip(starts, starts[1:], strict=False)
            if 0.15 < b - a < 2.5]
    bpm_hint = 90
    if gaps:
        med_gap = sorted(gaps)[len(gaps) // 2]
        for beats_per_gap in (1.0, 0.5, 2.0):
            bpm = 60.0 / (med_gap / beats_per_gap)
            if 60 <= bpm <= 174:
                bpm_hint = int(round(bpm))
                break

    # 置信度 = 有声帧占比与音符平均时长的加权（如实展示给用户决定是否采用）
    conf = min(1.0, 0.6 * voiced + 0.4 * min(1.0, MIN_NOTE_SEC * 10 / max(
        1e-9, sum(n["end"] - n["start"] for n in notes) / len(notes))))
    return {
        "notes": [{"start": round(n["start"], 2),
                   "dur": round(n["end"] - n["start"], 2),
                   "semi": semis[i]} for i, n in enumerate(notes)],
        "hum_melody": [[semis[i],
                        max(0.25, min(4.0, round((n["end"] - n["start"]) * bpm_hint / 60.0, 2)))]
                       for i, n in enumerate(notes)][:64],
        "bpm_hint": bpm_hint,
        "duration_sec": round(dur, 2),
        "note_count": len(notes),
        "confidence": round(conf, 2),
    }
