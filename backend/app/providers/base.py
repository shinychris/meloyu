"""Provider 协议 + 注册表（架构 §8）。"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from app.synth.ir import SongRequest

ProgressCallback = Callable[[str, int, str], None]   # (stage_key, pct 0-100, label_zh)
CancelCheck = Callable[[], bool]

STAGE_LABELS: dict[str, tuple[str, int, int]] = {
    # stage_key: (label, 进度区间)
    "writing": ("AI 写词", 2, 8),
    "structure": ("结构规划", 5, 10),
    "harmony": ("和声进行", 10, 20),
    "melody": ("旋律生成", 20, 35),
    "arrange": ("编曲与鼓点", 35, 50),
    "vocal": ("人声合成", 50, 65),
    "mixdown": ("混音渲染", 65, 85),
    "serialize": ("文件导出", 85, 95),
    "done": ("完成", 100, 100),
}


class SynthCancelled(Exception):
    """渲染循环在阶段边界检测到取消标志。"""


@runtime_checkable
class MusicProvider(Protocol):
    name: str
    display_name: str
    supports_vocals: bool

    def generate(
        self,
        request: SongRequest,
        progress: ProgressCallback,
        should_cancel: CancelCheck,
        dest_dir: str,
    ) -> GenerationOutput:
        """阻塞式执行（由 core.tasks 在线程池中调用）。"""
        ...


class CandidateArtifact:
    """单候选的产物元数据（文件已落盘，由 service 层登记 files 表）。

    quality_score 允许 None：外部模型候选不产出质量分（V1.3，ADR-012）。
    """

    def __init__(self, label: str, seed: int, quality_score: int | None, duration_sec: float,
                 structure: list[dict], style_tags: list[str], bpm: int,
                 tonic: str, mode: str, time_signature: str, vocal: str, language: str,
                 files: list[dict]):
        self.label = label
        self.seed = seed
        self.quality_score = quality_score
        self.duration_sec = duration_sec
        self.structure = structure
        self.style_tags = style_tags
        self.bpm = bpm
        self.tonic = tonic
        self.mode = mode
        self.time_signature = time_signature
        self.vocal = vocal
        self.language = language
        # files: [{relpath, kind, stem_name, mime, bytes, duration_sec, sample_rate, sha256}]
        self.files = files


class GenerationOutput:
    def __init__(self, candidates: list[CandidateArtifact], applied_negative: list[str],
                 inferred_structure: bool):
        self.candidates = candidates
        self.applied_negative = applied_negative
        self.inferred_structure = inferred_structure


# Provider 工厂已移至 services/model_center.get_music_provider（V1.3：DB 配置驱动，
# 支持 localsynth / api 双通道）；config.music_provider 环境变量随之废弃。
