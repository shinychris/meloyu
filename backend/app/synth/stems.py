"""分轨总线组装与相位对齐（架构 §7.8）。

四总线在同一采样网格分别求和 → 由构造保证相位对齐；
stems 混加与 master 的峰值差 ≤1dB（smoke test 断言）。
"""
from __future__ import annotations

import numpy as np

STEM_ORDER = ("vocals", "drums", "bass", "other")


def stems_mix(render_result) -> np.ndarray:
    """四 stem 混加（mono），用于与 master 中置对比。"""
    return sum(render_result.stems[name] for name in STEM_ORDER)


def peak_db(x: np.ndarray) -> float:
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    return 20.0 * np.log10(peak + 1e-12)


def phase_alignment_error_db(render_result) -> float:
    """stems 混加与 master(L/R 均值) 的峰值差（dB，应 ≤1dB）。"""
    mix = stems_mix(render_result)
    mid = (render_result.master_l + render_result.master_r) / 2.0
    return abs(peak_db(mix) - peak_db(mid))
