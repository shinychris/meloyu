"""LocalSynthProvider：确定性算法作曲 + numpy DSP 合成（架构 §7 八阶段管线）。

产物目录布局（dest_dir 为版本目录）：
  candidates/{A,B}/preview.mp3  master.wav  stems/{vocals,drums,bass,other}.wav  midi/*.mid
MIDI 随生成落盘但不登记 files 表（契约：candidate.files 固定 6 项，MIDI 经导出获取）。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np

from app.core.seed import candidate_seed
from app.providers.base import (
    STAGE_LABELS,
    CancelCheck,
    CandidateArtifact,
    GenerationOutput,
    ProgressCallback,
    SynthCancelled,
)
from app.synth import harmony as harmony_mod
from app.synth import melody as melody_mod
from app.synth import rhythm as rhythm_mod
from app.synth import structure as structure_mod
from app.synth.ir import SAMPLE_RATE, SongIR, SongRequest
from app.synth.midi_out import write_midi_files
from app.synth.mp3_io import encode_mp3
from app.synth.render import render_song
from app.synth.wav_io import write_wav

STEM_NAMES = ("vocals", "drums", "bass", "other")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _stage(progress: ProgressCallback, should_cancel: CancelCheck, key: str, pct: int):
    if should_cancel():
        raise SynthCancelled()
    label = STAGE_LABELS[key][0]
    progress(key, pct, label)


def _style_tags(style_prompt: str, family: str) -> list[str]:
    """由 style_prompt 派生风格标签（候选展示用）。"""
    tags = [t for t in re.split(r"[，,。;；\s]+", style_prompt or "") if t][:3]
    family_zh = {"pop": "流行", "guofeng": "国风", "edm": "电子", "hiphop": "嘻哈",
                 "lofi": "Lo-fi", "rock": "摇滚"}.get(family, "流行")
    if not any(family_zh in t for t in tags):
        tags.insert(0, family_zh)
    return tags[:4]


class LocalSynthProvider:
    name = "localsynth"
    display_name = "Meloyu 本地引擎"
    supports_vocals = True

    def generate(
        self,
        request: SongRequest,
        progress: ProgressCallback,
        should_cancel: CancelCheck,
        dest_dir: str,
    ) -> GenerationOutput:
        dest = Path(dest_dir)
        candidates: list[CandidateArtifact] = []
        applied_negative: list[str] = []
        inferred = False

        for label in ("A", "B"):
            seed = candidate_seed(request.seed, label)
            rng = np.random.default_rng(np.random.PCG64(seed))
            art = self._render_one(request, seed, rng, label, dest, progress, should_cancel)
            candidates.append(art)
            if label == "A":
                applied_negative = list(art.applied_negative_ext)
            inferred = inferred or art.inferred_ext
        return GenerationOutput(candidates, applied_negative, inferred)

    def _render_one(self, req: SongRequest, seed: int, rng: np.random.Generator,
                    label: str, dest: Path, progress: ProgressCallback,
                    should_cancel: CancelCheck) -> CandidateArtifact:
        ir = SongIR(req=req, seed=seed)

        _stage(progress, should_cancel, "structure", 7)
        parsed, has_tags = structure_mod.parse_lyrics(req.lyrics)
        structure_mod.build_structure(ir, parsed, has_tags)

        _stage(progress, should_cancel, "harmony", 15)
        harmony_mod.build_harmony(ir, rng)

        _stage(progress, should_cancel, "melody", 28)
        melody_mod.compose_melody(ir, rng)

        _stage(progress, should_cancel, "arrange", 42)
        rhythm_mod.build_rhythm(ir, rng)

        _stage(progress, should_cancel, "vocal", 57)
        # 人声在 render 阶段内完成合成（bus 内写入），此处仅作阶段推进
        result = None

        _stage(progress, should_cancel, "mixdown", 75)
        result = render_song(ir, rng)

        _stage(progress, should_cancel, "serialize", 90)
        cand_dir = dest / "candidates" / label
        files: list[dict] = []

        # preview.mp3（192k 立体声）
        p = cand_dir / "preview.mp3"
        size = encode_mp3(p, result.master_l, result.master_r, bitrate=192)
        files.append(dict(relpath=p.relative_to(dest).as_posix(), kind="preview",
                          stem_name=None, mime="audio/mpeg", bytes=size,
                          duration_sec=round(ir.total_sec, 2), sample_rate=SAMPLE_RATE,
                          sha256=_sha256_file(p)))
        # master.wav（24bit 立体声）
        p = cand_dir / "master.wav"
        size = write_wav(p, [result.master_l, result.master_r], bits=24)
        files.append(dict(relpath=p.relative_to(dest).as_posix(), kind="master",
                          stem_name=None, mime="audio/wav", bytes=size,
                          duration_sec=round(ir.total_sec, 2), sample_rate=SAMPLE_RATE,
                          sha256=_sha256_file(p)))
        # stems（24bit 单声道，四轨）
        for stem in STEM_NAMES:
            p = cand_dir / "stems" / f"{stem}.wav"
            size = write_wav(p, [result.stems[stem]], bits=24)
            files.append(dict(relpath=p.relative_to(dest).as_posix(), kind="stem",
                              stem_name=stem, mime="audio/wav", bytes=size,
                              duration_sec=round(ir.total_sec, 2), sample_rate=SAMPLE_RATE,
                              sha256=_sha256_file(p)))
        # MIDI（落盘不登记）
        write_midi_files(ir, cand_dir / "midi")

        quality = self._quality_score(seed, label)
        art = CandidateArtifact(
            label=label, seed=seed, quality_score=quality,
            duration_sec=round(ir.total_sec, 2), structure=ir.structure_json(),
            style_tags=_style_tags(req.style_prompt, ir.style_family),
            bpm=req.bpm, tonic=req.tonic, mode=req.mode,
            time_signature=req.time_signature, vocal=req.vocal, language=req.language,
            files=files,
        )
        art.applied_negative_ext = ir.applied_negative
        art.inferred_ext = ir.inferred_structure
        return art

    @staticmethod
    def _quality_score(seed: int, label: str) -> int:
        """质量分：种子哈希派生（确定性），B 略低于 A。"""
        h = int.from_bytes(hashlib.sha256(f"{seed}:{label}".encode()).digest()[:2], "big")
        base = 78 + h % 15
        if label == "B":
            base -= 3 + (h >> 8) % 4
        return max(60, min(98, base))


def derive_candidate_seed(seed: int, label: str) -> int:
    return candidate_seed(seed, label)
