"""WAV 读写（stdlib wave）：16bit 预览中间格式 / 24bit 母带与分轨。"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from app.core.i18n import tr
from app.synth.ir import SAMPLE_RATE


def _to_int32(x: np.ndarray, bits: int) -> np.ndarray:
    """float [-1,1] → 定点整型，存于 int32 容器（24bit 时高 8 位为 0）。"""
    peak = 1 << (bits - 1)
    scaled = np.clip(x, -1.0, 1.0 - 1e-9) * peak
    vals = np.round(scaled).astype("<i4")
    if bits == 24:
        vals = vals & 0x00FFFFFF
        # 符号扩展到 int32 语义上仍在 24bit 范围内，写盘时只取低 3 字节
    return vals


def write_wav(path: str | Path, channels: list[np.ndarray], bits: int = 24,
              sample_rate: int = SAMPLE_RATE) -> int:
    """写 WAV（interleave 多声道）；返回字节数。确定性：无时间戳进入文件。"""
    assert channels, tr("至少一个声道", "at least one channel required")
    n = max(len(c) for c in channels)
    ints = [_to_int32(np.resize(c, n) if len(c) < n else c, bits) for c in channels]
    interleaved = np.stack(ints, axis=-1)
    if bits == 24:
        raw = interleaved.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
        sampwidth = 3
    else:
        raw = interleaved.astype("<i2" if bits == 16 else "<i4").tobytes()
        sampwidth = bits // 8
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(len(channels))
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(raw)
    return path.stat().st_size


def read_wav(path: str | Path) -> list[np.ndarray]:
    """读 WAV → 各声道 float [-1,1] 数组列表（write_wav 的逆操作，逐样本无损）。

    24bit 定点 ↔ float 往返精确（|v| < 2^53 内浮点乘除无损），保证
    regen-section 复制非选区采样后重新写盘字节级不变（验收基础）。
    """
    with wave.open(str(path), "rb") as wf:
        ch, sw = wf.getnchannels(), wf.getsampwidth()
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if sr != SAMPLE_RATE:
        raise ValueError(tr(f"采样率不符（{sr} != {SAMPLE_RATE}）：{path}",
                       f"sample rate mismatch ({sr} != {SAMPLE_RATE}): {path}"))
    if sw == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        data = v.astype(np.float64) / float(1 << 23)
    else:
        dt = "<i2" if sw == 2 else "<i4"
        data = np.frombuffer(raw, dtype=dt).astype(np.float64) / float(1 << (8 * sw - 1))
    if ch == 1:
        return [data]
    return [data[i::ch] for i in range(ch)]
