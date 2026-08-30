"""WAV 写盘（stdlib wave）：16bit 预览中间格式 / 24bit 母带与分轨。"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

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
    assert channels, "至少一个声道"
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
