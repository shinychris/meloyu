"""LocalSynthProvider：确定性算法作曲 + numpy DSP 合成（架构 §7 八阶段管线）。

产物目录布局（dest_dir 为版本目录）：
  candidates/{A,B}/preview.mp3  master.wav  stems/{vocals,drums,bass,other}.wav  midi/*.mid
MIDI 随生成落盘但不登记 files 表（契约：candidate.files 固定 6 项，MIDI 经导出获取）。

V1.1：generate_derived 承接 extend/variant/regen-section 三种派生操作
（编排见 services/editing.py，波形装配见 synth/editing.py）。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from pathlib import Path

import numpy as np

from app.config import GENERATION_TASK_TIMEOUT_SEC
from app.core.i18n import tr
from app.core.seed import candidate_seed
from app.providers.base import (
    CancelCheck,
    CandidateArtifact,
    GenerationOutput,
    ProgressCallback,
    SynthCancelled,
    stage_label,
)
from app.synth import editing as editing_mod
from app.synth import harmony as harmony_mod
from app.synth import melody as melody_mod
from app.synth import rhythm as rhythm_mod
from app.synth import structure as structure_mod
from app.synth.ir import SAMPLE_RATE, SongIR, SongRequest
from app.synth.midi_out import write_midi_files
from app.synth.mp3_io import encode_mp3
from app.synth.render import render_song
from app.synth.wav_io import read_wav, write_wav

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
    progress(key, pct, stage_label(key))


def _style_tags(style_prompt: str, family: str) -> list[str]:
    """由 style_prompt 派生风格标签（候选展示用）；家族兜底标签按当前 locale。"""
    tags = [t for t in re.split(r"[，,。;；\s]+", style_prompt or "") if t][:3]
    families = {"pop": ("流行", "pop"), "guofeng": ("国风", "Chinese traditional"),
                "edm": ("电子", "electronic"), "hiphop": ("嘻哈", "hip-hop"),
                "lofi": ("Lo-fi", "Lo-fi"), "rock": ("摇滚", "rock")}
    zh, en = families.get(family, families["pop"])
    family_label = tr(zh, en)
    if not any(family_label in t for t in tags):
        tags.insert(0, family_label)
    return tags[:4]


def _base_request(spec: dict) -> SongRequest:
    """由派生任务快照（base_params/base_lyrics/base_seed）重建源候选 SongRequest。"""
    p = spec.get("base_params") or {}
    key = p.get("key") or {}
    return SongRequest(
        style_prompt=p.get("style_prompt", ""), negative_prompt=p.get("negative_prompt", ""),
        model=p.get("model", "v1_pro"), lyrics=spec.get("base_lyrics") or "",
        bpm=p.get("bpm", 90), tonic=key.get("tonic", "A"), mode=key.get("mode", "minor"),
        time_signature=p.get("time_signature", "4/4"),
        duration_sec=p.get("duration_sec", 210),
        vocal=p.get("vocal", "female_air"), language=p.get("language", "zh"),
        instrument_density=p.get("instrument_density", 65),
        seed=int(spec.get("base_seed", 0)),
    )


def _write_candidate_files(dest: Path, label: str, master_l: np.ndarray,
                           master_r: np.ndarray, stems: dict[str, np.ndarray],
                           total_sec: float, ir: SongIR) -> list[dict]:
    """落盘单候选六件产物（preview/master/4 stems）+ MIDI 四轨（不登记 files 表）。"""
    cand_dir = dest / "candidates" / label
    files: list[dict] = []
    # preview.mp3（192k 立体声）
    p = cand_dir / "preview.mp3"
    size = encode_mp3(p, master_l, master_r, bitrate=192)
    files.append(dict(relpath=p.relative_to(dest).as_posix(), kind="preview",
                      stem_name=None, mime="audio/mpeg", bytes=size,
                      duration_sec=round(total_sec, 2), sample_rate=SAMPLE_RATE,
                      sha256=_sha256_file(p)))
    # master.wav（24bit 立体声）
    p = cand_dir / "master.wav"
    size = write_wav(p, [master_l, master_r], bits=24)
    files.append(dict(relpath=p.relative_to(dest).as_posix(), kind="master",
                      stem_name=None, mime="audio/wav", bytes=size,
                      duration_sec=round(total_sec, 2), sample_rate=SAMPLE_RATE,
                      sha256=_sha256_file(p)))
    # stems（24bit 单声道，四轨）
    for stem in STEM_NAMES:
        p = cand_dir / "stems" / f"{stem}.wav"
        size = write_wav(p, [stems[stem]], bits=24)
        files.append(dict(relpath=p.relative_to(dest).as_posix(), kind="stem",
                          stem_name=stem, mime="audio/wav", bytes=size,
                          duration_sec=round(total_sec, 2), sample_rate=SAMPLE_RATE,
                          sha256=_sha256_file(p)))
    # MIDI（落盘不登记）
    write_midi_files(ir, cand_dir / "midi")
    return files


class LocalSynthProvider:
    name = "localsynth"
    @property
    def display_name(self) -> str:
        return tr("Meloyu 本地引擎", "Meloyu local engine")
    supports_vocals = True
    timeout_sec = GENERATION_TASK_TIMEOUT_SEC

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
        files = _write_candidate_files(dest, label, result.master_l, result.master_r,
                                       result.stems, ir.total_sec, ir)

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

    # ---------- V1.1 派生操作（extend / variant / regen-section） ----------

    def generate_derived(
        self,
        request: SongRequest,
        spec: dict,
        base_dir: str,
        progress: ProgressCallback,
        should_cancel: CancelCheck,
        dest_dir: str,
    ) -> GenerationOutput:
        """派生生成入口。spec 由 services/editing.py 组装（含源候选上下文）。"""
        dest = Path(dest_dir)
        op = spec["op"]
        base_req = _base_request(spec)
        if op == "extend":
            art, inferred = self._derive_extend(request, spec, base_req, base_dir, dest,
                                                progress, should_cancel)
        elif op == "variant":
            art, inferred = self._derive_variant(request, spec, base_req, dest,
                                                 progress, should_cancel)
        elif op == "regen_section":
            art, inferred = self._derive_regen(request, spec, base_req, base_dir, dest,
                                               progress, should_cancel)
        else:
            raise ValueError(tr(f"未知派生操作：{op}", f"Unknown derived operation: {op}"))
        return GenerationOutput([art], list(art.applied_negative_ext), inferred)

    def _derive_extend(self, request: SongRequest, spec: dict, base_req: SongRequest,
                       base_dir: str, dest: Path, progress: ProgressCallback,
                       should_cancel: CancelCheck) -> tuple[CandidateArtifact, bool]:
        """续写：重建原曲 IR（含音符，供 MIDI 合成）→ 渲染续写段 → 交叉淡化拼接。"""
        _stage(progress, should_cancel, "structure", 10)
        base_ir = editing_mod.rebuild_ir(base_req, base_req.seed)
        if not editing_mod.structure_matches(base_ir, spec.get("base_structure") or []):
            raise ValueError(tr("源候选结构重建与存库不一致，无法续写",
                       "Rebuilt source structure does not match stored data; cannot extend"))

        _stage(progress, should_cancel, "harmony", 25)
        rng = editing_mod.make_rng(request.seed)
        req_ext = replace(request, duration_sec=int(spec.get("seconds", 15)))
        ext_ir = editing_mod.build_tail_ir(req_ext, rng, base_ir)

        _stage(progress, should_cancel, "melody", 40)
        _stage(progress, should_cancel, "arrange", 55)
        _stage(progress, should_cancel, "vocal", 65)
        _stage(progress, should_cancel, "mixdown", 78)
        result = render_song(ext_ir, rng)

        _stage(progress, should_cancel, "serialize", 90)
        cand_dir = Path(base_dir)  # base_dir 已指向源候选目录（…/candidates/{label}）
        orig_master = read_wav(cand_dir / "master.wav")
        orig_stems = {s: read_wav(cand_dir / "stems" / f"{s}.wav")[0] for s in STEM_NAMES}
        xf = int(editing_mod.CROSSFADE_SEC * SAMPLE_RATE)
        new_l = editing_mod.crossfade_concat(orig_master[0], result.master_l, xf)
        new_r = editing_mod.crossfade_concat(orig_master[1], result.master_r, xf)
        new_stems = {s: editing_mod.crossfade_concat(orig_stems[s], result.stems[s], xf)
                     for s in STEM_NAMES}
        total_sec = len(new_l) / SAMPLE_RATE

        ir_full = editing_mod.merge_ir_for_midi(base_ir, ext_ir)
        files = _write_candidate_files(dest, "A", new_l, new_r, new_stems, total_sec, ir_full)
        tail_type = ext_ir.sections[0].section if ext_ir.sections else "outro"
        structure = base_ir.structure_json() + [{
            "section": tail_type, "bars": ext_ir.total_bars,
            "start_bar": base_ir.total_bars,
            "start_sec": round(len(orig_master[0]) / SAMPLE_RATE, 2),
            "end_sec": round(total_sec, 2),
        }]
        art = CandidateArtifact(
            label="A", seed=request.seed,
            quality_score=self._quality_score(request.seed, "A"),
            duration_sec=round(total_sec, 2), structure=structure,
            style_tags=_style_tags(base_req.style_prompt, base_ir.style_family),
            bpm=base_req.bpm, tonic=base_req.tonic, mode=base_req.mode,
            time_signature=base_req.time_signature, vocal=base_req.vocal,
            language=base_req.language, files=files,
        )
        art.applied_negative_ext = ext_ir.applied_negative
        art.inferred_ext = base_ir.inferred_structure
        return art, base_ir.inferred_structure

    def _derive_variant(self, request: SongRequest, spec: dict, base_req: SongRequest,
                        dest: Path, progress: ProgressCallback,
                        should_cancel: CancelCheck) -> tuple[CandidateArtifact, bool]:
        """变奏：结构逐段沿用（先与存库校验），新 style_prompt 重作和声/旋律/编曲。"""
        _stage(progress, should_cancel, "structure", 10)
        base_ir = editing_mod.rebuild_ir(base_req, base_req.seed, with_notes=False)
        if not editing_mod.structure_matches(base_ir, spec.get("base_structure") or []):
            base_ir.sections = editing_mod.sections_from_structure(
                spec.get("base_structure") or [])

        _stage(progress, should_cancel, "harmony", 25)
        rng = editing_mod.make_rng(request.seed)
        ir = editing_mod.build_variant_ir(request, base_ir,
                                          spec.get("base_structure") or [], rng)

        _stage(progress, should_cancel, "melody", 40)
        _stage(progress, should_cancel, "arrange", 55)
        _stage(progress, should_cancel, "vocal", 65)
        _stage(progress, should_cancel, "mixdown", 78)
        result = render_song(ir, rng)

        _stage(progress, should_cancel, "serialize", 90)
        files = _write_candidate_files(dest, "A", result.master_l, result.master_r,
                                       result.stems, ir.total_sec, ir)
        art = CandidateArtifact(
            label="A", seed=request.seed,
            quality_score=self._quality_score(request.seed, "A"),
            duration_sec=round(ir.total_sec, 2), structure=ir.structure_json(),
            style_tags=_style_tags(request.style_prompt, ir.style_family),
            bpm=ir.req.bpm, tonic=ir.req.tonic, mode=ir.req.mode,
            time_signature=ir.req.time_signature, vocal=ir.req.vocal,
            language=ir.req.language, files=files,
        )
        art.applied_negative_ext = ir.applied_negative
        art.inferred_ext = base_ir.inferred_structure
        return art, base_ir.inferred_structure

    def _derive_regen(self, request: SongRequest, spec: dict, base_req: SongRequest,
                      base_dir: str, dest: Path, progress: ProgressCallback,
                      should_cancel: CancelCheck) -> tuple[CandidateArtifact, bool]:
        """段落重生成：整曲重渲染（仅目标出现的段落换新）→ 其余段逐样本复制回原候选。"""
        _stage(progress, should_cancel, "structure", 10)
        base_ir = editing_mod.rebuild_ir(base_req, base_req.seed)
        structure = spec.get("base_structure") or []
        if not editing_mod.structure_matches(base_ir, structure):
            raise ValueError(tr("源候选结构重建与存库不一致，无法重生成段落",
                       "Rebuilt source structure does not match stored data; cannot regenerate section"))
        occurrence = int(spec.get("occurrence", 1))
        target_index = editing_mod.section_occurrence_index(structure, spec["section"],
                                                            occurrence)
        if target_index is None:
            raise ValueError(tr(f"occurrence 越界：段落 {spec['section']}",
                       f"occurrence out of range: section {spec['section']}"))

        _stage(progress, should_cancel, "harmony", 25)
        rng = editing_mod.make_rng(request.seed)
        ir = editing_mod.regenerate_sections(base_ir, spec["section"], occurrence, rng)

        _stage(progress, should_cancel, "melody", 40)
        _stage(progress, should_cancel, "arrange", 55)
        _stage(progress, should_cancel, "vocal", 65)
        _stage(progress, should_cancel, "mixdown", 78)
        result = render_song(ir, rng)

        _stage(progress, should_cancel, "serialize", 90)
        cand_dir = Path(base_dir)  # base_dir 已指向源候选目录（…/candidates/{label}）
        orig_master = read_wav(cand_dir / "master.wav")
        orig_stems = {s: read_wav(cand_dir / "stems" / f"{s}.wav")[0] for s in STEM_NAMES}
        n = len(orig_master[0])
        if len(result.master_l) != n:
            raise ValueError(tr(f"重渲染长度不一致：{len(result.master_l)} vs {n}",
                       f"Re-render length mismatch: {len(result.master_l)} vs {n}"))
        new_l = editing_mod.splice_regen(result.master_l, orig_master[0], structure,
                                         target_index)
        new_r = editing_mod.splice_regen(result.master_r, orig_master[1], structure,
                                         target_index)
        new_stems = {s: editing_mod.splice_regen(result.stems[s], orig_stems[s],
                                                 structure, target_index)
                     for s in STEM_NAMES}
        total_sec = n / SAMPLE_RATE
        files = _write_candidate_files(dest, "A", new_l, new_r, new_stems, total_sec, ir)
        art = CandidateArtifact(
            label="A", seed=request.seed,
            quality_score=self._quality_score(request.seed, "A"),
            duration_sec=round(total_sec, 2), structure=[dict(seg) for seg in structure],
            style_tags=_style_tags(base_req.style_prompt, base_ir.style_family),
            bpm=base_req.bpm, tonic=base_req.tonic, mode=base_req.mode,
            time_signature=base_req.time_signature, vocal=base_req.vocal,
            language=base_req.language, files=files,
        )
        art.applied_negative_ext = ir.applied_negative
        art.inferred_ext = base_ir.inferred_structure
        return art, base_ir.inferred_structure


def derive_candidate_seed(seed: int, label: str) -> int:
    return candidate_seed(seed, label)
