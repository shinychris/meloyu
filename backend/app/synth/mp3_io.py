"""lameenc 封装：320k 母带导出 / 192k 预览。"""
from __future__ import annotations

from pathlib import Path

import lameenc
import numpy as np

from app.synth.ir import SAMPLE_RATE


def encode_mp3(path: str | Path, left: np.ndarray, right: np.ndarray,
               bitrate: int = 192, sample_rate: int = SAMPLE_RATE) -> int:
    """float 立体声 → MP3 CBR。确定性：LAME 相同输入/参数输出一致。"""
    n = max(len(left), len(right))
    ch_l = np.resize(left, n) if len(left) < n else left
    ch_r = np.resize(right, n) if len(right) < n else right
    interleaved = np.empty(n * 2)
    interleaved[0::2] = np.clip(ch_l, -1.0, 1.0 - 1e-9) * 32767.0
    interleaved[1::2] = np.clip(ch_r, -1.0, 1.0 - 1e-9) * 32767.0
    pcm = np.round(interleaved).astype("<i2").tobytes()

    enc = lameenc.Encoder()
    enc.set_bit_rate(bitrate)
    enc.set_in_sample_rate(sample_rate)
    enc.set_channels(2)
    enc.set_quality(2)
    data = enc.encode(pcm) + enc.flush()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(data))
    return path.stat().st_size
