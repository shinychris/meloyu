"""确定性种子派生（架构 §7.9）。

规则：canonical_json(params) + ":" + server_nonce → SHA-256 → 低 32 位 uint32。
候选 A 用 seed，候选 B 用 seed XOR 0x9E3779B9。
SERVER_NONCE 取 config 常量（默认固定值），保证跨重启可复现。
"""
from __future__ import annotations

import hashlib
import json

GOLDEN_RATIO = 0x9E3779B9
_MASK32 = 0xFFFFFFFF


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def derive_seed(params: dict, server_nonce: str) -> int:
    canonical = canonical_json(params)
    digest = hashlib.sha256((canonical + ":" + server_nonce).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & _MASK32


def candidate_seed(seed: int, label: str) -> int:
    if label == "A":
        return seed & _MASK32
    return (seed ^ GOLDEN_RATIO) & _MASK32


def cover_color_for_seed(seed: int) -> str:
    """封面色块：种子派生调色板取色（契约 work.cover_color）。"""
    palette = [
        "#232323", "#1c2b1f", "#2b2118", "#1f2430", "#262626",
        "#2a1a22", "#1a2a26", "#221a2a", "#1d2032", "#2d2418",
    ]
    return palette[seed % len(palette)]
