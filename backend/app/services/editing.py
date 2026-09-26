"""V1.1 派生生成服务：extend / variant / regen-section 提交编排。

统一走既有任务管线（type=generation 线程池、按价目扣积分、失败退款、轮询取消），
在源候选所属 work 下建子版本（parent=源版本，source=对应枚举）；
成功后由 generation._persist_success 自动 adopt 新候选为该子版本活跃候选。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import EDIT_OPERATION_CREDIT_COST, settings
from app.core.errors import err_conflict, err_validation
from app.core.i18n import tr
from app.models import Candidate, File, Task, User, Version, Work
from app.models.base import utc_now_iso
from app.services import generation as gen_svc
from app.services import works as works_svc
from app.services.serializers import task_to_dict
from app.synth.editing import derive_op_seed

DERIVED_OPS = ("extend", "variant", "regen_section", "retune",
               "pitch_edit")  # v0.9.0 增 retune；v0.11.0 增 pitch_edit（/pitch）
MAX_TOTAL_DURATION_SEC = 240  # 与契约 generation_limits.max_duration_sec 一致


def _source_context(db: Session, user: User, candidate_id: str,
                    ) -> tuple[Candidate, Version, Work]:
    """取源候选并校验产物完整（衍生需读原音频做拼接）。"""
    cand = gen_svc.get_candidate_owned(db, candidate_id, user)
    version = db.get(Version, cand.version_id)
    work = db.get(Work, version.work_id)
    rows = db.execute(select(File.kind, File.stem_name)
                      .where(File.candidate_id == cand.id)).all()
    have = {(kind, stem) for kind, stem in rows}
    required = {("master", None), ("preview", None)} | {
        ("stem", s) for s in ("vocals", "drums", "bass", "other")}
    if not required.issubset(have):
        if not any(kind == "stem" for kind, _ in have):
            raise err_conflict(
                tr("外部模型候选不含分轨文件，暂不支持延长/变体/段落重生成",
                  "External-model candidates have no stems; extend/variant/section-regen "
                  "are not supported yet"))
        raise err_conflict(tr("源候选产物不完整，无法衍生",
                             "Source candidate artifacts incomplete; cannot derive"))
    base_dir = settings.audio_path / work.id / version.id / "candidates" / cand.label
    for rel in ("master.wav", "preview.mp3",
                "stems/vocals.wav", "stems/drums.wav", "stems/bass.wav", "stems/other.wav"):
        if not (base_dir / rel).exists():
            raise err_conflict(tr("源候选音频文件缺失，无法衍生",
                                 "Source candidate audio files missing; cannot derive"))
    return cand, version, work


def _base_params(version: Version, cand: Candidate) -> dict:
    """源版本 params 快照（缺列时以候选落库值兜底，不编造字段）。"""
    p = dict(version.params or {})
    key = dict(p.get("key") or {})
    return {
        "mode": p.get("mode", "custom"),
        "style_prompt": p.get("style_prompt", ""),
        "negative_prompt": p.get("negative_prompt", ""),
        "model": p.get("model", "v1_pro"),
        "bpm": p.get("bpm", cand.bpm),
        "key": {"tonic": key.get("tonic", cand.key_tonic),
                "mode": key.get("mode", cand.key_mode)},
        "time_signature": p.get("time_signature", cand.time_signature),
        "duration_sec": p.get("duration_sec", cand.duration_sec),
        "vocal": p.get("vocal", cand.vocal),
        "language": p.get("language", cand.language),
        "instrument_density": p.get("instrument_density", 65),
    }


def submit_derived(db: Session, user: User, candidate_id: str, op: str, *,
                   seconds: int | None = None, style_prompt: str | None = None,
                   section: str | None = None, occurrence: int = 1,
                   bpm: int | None = None, key: dict | None = None,
                   note_edits: list | None = None, quantize: str = "off") -> dict:
    """提交派生生成：建子版本 + 任务 + 扣积分，返回 POST /generations 同构响应。"""
    if op not in DERIVED_OPS:
        raise err_validation(tr(f"未知派生操作：{op}", f"Unknown derived operation: {op}"))
    from app.services.generation import _check_maintenance
    _check_maintenance()
    from app.core.disk_guard import ensure_disk_available
    ensure_disk_available()
    cand, version, work = _source_context(db, user, candidate_id)
    params = _base_params(version, cand)
    extra = ""

    if op == "extend":
        total = cand.duration_sec + int(seconds or 0)
        if total > MAX_TOTAL_DURATION_SEC:
            raise err_validation(
                tr(f"续写后总时长 {total}s 超过 {MAX_TOTAL_DURATION_SEC}s 上限",
                   f"Total duration after extend is {total}s, exceeding the "
                   f"{MAX_TOTAL_DURATION_SEC}s limit"))
        params["duration_sec"] = total
        extra = str(int(seconds or 0))
    elif op == "variant":
        params["style_prompt"] = style_prompt or ""
        params["mode"] = "custom"
        extra = style_prompt or ""
        if style_prompt:
            from app.providers.lyrics_local import check_sensitive
            if check_sensitive(style_prompt):
                from app.core.errors import err_sensitive
                raise err_sensitive()
    elif op == "retune":
        # V2 多轨编辑器（v0.9.0）：变速/变调——确定性引擎同 seed 重渲染（素材一致）
        from app.models.enums import KEY_MODES, TONICS
        if bpm is None and not key:
            raise err_validation(
                tr("retune 需要至少 bpm 或 key 之一", "retune needs at least bpm or key"))
        if bpm is not None:
            if not 60 <= int(bpm) <= 174:
                raise err_validation(
                    tr("bpm 必须在 60~174", "bpm must be within 60-174"))
            params["bpm"] = int(bpm)
        if key:
            tonic = str(key.get("tonic", params["key"]["tonic"])).upper()
            mode = str(key.get("mode", params["key"]["mode"])).lower()
            if tonic not in TONICS or mode not in KEY_MODES:
                raise err_validation(tr("key 无效（tonic/mode）", "invalid key (tonic/mode)"))
            params["key"] = {"tonic": tonic, "mode": mode}
        extra = f"{params['bpm']}:{params['key']['tonic']}{params['key']['mode']}"
    elif op == "pitch_edit":
        # /pitch 修调（v0.11.0）：音符级移调 + 可选节奏量化，同 seed 确定性重渲染
        edits = note_edits or []
        if not 1 <= len(edits) <= 200:
            raise err_validation(tr(f"音符编辑须为 1~200 条（收到 {len(edits)}）",
                                f"Note edits must be 1-200 items (got {len(edits)})"))
        for e in edits:
            try:
                beat, semi = float(e["beat"]), int(e["semi"])
            except (KeyError, TypeError, ValueError) as e:
                raise err_validation(tr("每条编辑须为 {beat, semi}",
                                     "Each edit must be {beat, semi}")) from e
            if not 0 <= beat <= 10000 or not -12 <= semi <= 12:
                raise err_validation(tr("beat 须 0~10000、semi 须 -12~12",
                                     "beat must be 0-10000 and semi must be -12 to 12"))
        if quantize not in ("off", "8", "16"):
            raise err_validation(tr("quantize 须为 off/8/16",
                                 "quantize must be off/8/16"))
        extra = f"{len(edits)}:{quantize}"
    elif op == "regen_section":
        seg_sections = {str(seg.get("section")) for seg in (cand.structure or [])}
        if section not in seg_sections:
            raise err_validation(
                tr(f"候选结构中不存在该段落：{section}（可用：{sorted(seg_sections)}）",
                   f"Section not found in candidate structure: {section} "
                   f"(available: {sorted(seg_sections)})"))
        n_occ = sum(1 for seg in (cand.structure or [])
                    if str(seg.get("section")) == section)
        if not 1 <= occurrence <= n_occ:
            raise err_validation(
                tr(f"occurrence 越界：段落 {section} 共出现 {n_occ} 次，合法范围 1~{n_occ}",
                   f"occurrence out of range: section {section} occurs {n_occ} time(s), "
                   f"valid range 1-{n_occ}"),
                details=[{"field": "occurrence", "message": f"1-{n_occ}"}])
        extra = f"{section}:{occurrence}"

    gen_svc.check_free_daily_limit(db, user)  # 派生同样计入免费档每日生成限额

    seed = derive_op_seed(cand.seed, op, extra)
    now = utc_now_iso()
    child = Version(work_id=work.id, parent_version_id=version.id,
                    version_no=f"v{work.version_count + 1}", source=op,
                    candidate_count=0, params=params,
                    lyrics=version.lyrics or "", created_at=now, updated_at=now)
    db.add(child)
    db.flush()
    work.version_count += 1
    work.updated_at = now

    derived_spec: dict = {
        "op": op,
        "source_candidate_id": cand.id,
        "base_seed": cand.seed,
        "base_params": _base_params(version, cand),
        "base_lyrics": version.lyrics or "",
        "base_structure": cand.structure or [],
        "base_dir": f"{work.id}/{version.id}/candidates/{cand.label}",
        "base_label": cand.label,
    }
    if op == "extend":
        derived_spec["seconds"] = int(seconds or 0)
    elif op == "variant":
        derived_spec["style_prompt"] = style_prompt or ""
    elif op == "regen_section":
        derived_spec["section"] = section or ""
        derived_spec["occurrence"] = int(occurrence)
    elif op == "retune":
        derived_spec["retune_bpm"] = params["bpm"]
        derived_spec["retune_key"] = dict(params["key"])
    elif op == "pitch_edit":
        derived_spec["note_edits"] = [
            {"beat": float(e["beat"]), "semi": int(e["semi"])} for e in (note_edits or [])]
        derived_spec["quantize"] = quantize

    cost = EDIT_OPERATION_CREDIT_COST.get(op, 6)
    task = Task(user_id=user.id, type="generation", status="queued", progress=0,
                stage_key="queued", stage_label=tr("排队中", "Queued"), work_id=work.id,
                version_id=child.id, provider="localsynth", seed=seed,
                cost_credits=cost,
                request_payload={
                    "_derived": derived_spec,
                    "_resolved": {"params": params, "lyrics": version.lyrics or "",
                                  "seed": seed},
                },
                created_at=now, updated_at=now)
    db.add(task)
    db.flush()

    from app.services.credits import atomic_deduct
    atomic_deduct(db, user.id, cost, "generation", task.id)

    db.commit()
    db.refresh(task)
    db.refresh(work)

    from app.core.tasks import schedule_generation
    schedule_generation(task.id, plan=user.plan)

    return {
        "task": task_to_dict(task),
        "work": {"id": work.id, "display_code": work.display_code,
                 "title": work.title, "cover_color": work.cover_color},
        "cost_credits": cost,
    }


def submit_extend(db: Session, user: User, candidate_id: str, seconds: int) -> dict:
    return submit_derived(db, user, candidate_id, "extend", seconds=seconds)


def submit_variant(db: Session, user: User, candidate_id: str, style_prompt: str) -> dict:
    return submit_derived(db, user, candidate_id, "variant", style_prompt=style_prompt)


def submit_regen_section(db: Session, user: User, candidate_id: str, section: str,
                         occurrence: int = 1) -> dict:
    return submit_derived(db, user, candidate_id, "regen_section", section=section,
                          occurrence=occurrence)


def submit_retune(db: Session, user: User, candidate_id: str, bpm: int | None,
                  key: dict | None) -> dict:
    """V2 编辑器：变速/变调（同 seed 确定性重渲染，子版本 source=retune）。"""
    return submit_derived(db, user, candidate_id, "retune", bpm=bpm, key=key)


def submit_pitch_edit(db: Session, user: User, candidate_id: str,
                      note_edits: list, quantize: str = "off") -> dict:
    """V2 /pitch 修调：音符级移调/量化（同 seed 确定性重渲染，子版本 source=pitch_edit）。"""
    return submit_derived(db, user, candidate_id, "pitch_edit",
                          note_edits=note_edits, quantize=quantize)


def submit_mixdown(db: Session, user: User, version_id: str, wav: bytes,
                   notes: str = "") -> dict:
    """V2 编辑器混音回存（v0.9.0）：浏览器多轨编辑（音量/EQ）OfflineAudioContext
    渲染的成品 wav → 子版本（source=mixdown，1 候选自动采用）。

    人类参与留痕：EQ/音量决策=人类编辑（事件 detail 携带 notes），证书
    human_participation 计入；不扣积分（渲染在客户端完成）。
    """
    from app.services.export import _wav_bytes_to_float
    version = works_svc.get_version_owned(db, version_id, user)
    if not version.active_candidate_id:
        raise err_conflict(tr("该版本尚未采用候选", "No candidate adopted for this version yet"))
    if len(wav) > 200 * 1024 * 1024:
        raise err_validation(tr("混音文件超过 200MB 上限", "Mixdown exceeds the 200MB limit"))
    from app.core.disk_guard import ensure_disk_available
    ensure_disk_available(extra_bytes=len(wav))
    import hashlib
    import wave as wav_mod

    from app.config import settings
    from app.models import File as FileRow
    work = db.get(Work, version.work_id)
    try:
        with wav_mod.open(__import__("io").BytesIO(wav), "rb") as wf:
            n, ch, sw, sr = wf.getnframes(), wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
            raw = wf.readframes(n)
    except Exception as e:  # noqa: BLE001
        raise err_validation(tr(f"wav 无法解析：{e}", f"cannot parse wav: {e}")) from e
    duration = round(n / sr, 2)
    # 与 works.duration CHECK(30~240) 对齐——编辑器不改变歌曲时长量级
    if duration < 30 or duration > 240:
        raise err_validation(tr(f"混音时长 {duration}s 越界（30~240s）",
                            f"Mixdown duration {duration}s out of range (30-240s)"))

    data = _wav_bytes_to_float(raw, sw)
    if ch == 1:
        left = right = data
    else:
        left, right = data[0::2], data[1::2]

    now = utc_now_iso()
    child = Version(work_id=work.id, parent_version_id=version.id,
                    version_no=f"v{work.version_count + 1}", source="mixdown",
                    candidate_count=0, params=dict(version.params or {}),
                    lyrics=version.lyrics or "", created_at=now, updated_at=now)
    db.add(child)
    db.flush()
    work.version_count += 1
    work.updated_at = now
    cand = Candidate(
        version_id=child.id, label="A", adopted=True, seed=0,
        quality_score=None,  # 人工混音不产 AI 质量分（不造假分）
        duration_sec=int(duration), bpm=version.params.get("bpm", 90) if isinstance(version.params, dict) else 90,
        key_tonic=work.key_tonic, key_mode=work.key_mode,
        time_signature=(version.params or {}).get("time_signature", "4/4"),
        vocal=(version.params or {}).get("vocal", "female_air"),
        language=(version.params or {}).get("language", "zh"),
        style_tags=["mixdown"], structure=[],
        created_at=now, updated_at=now)
    db.add(cand)
    db.flush()
    child.active_candidate_id = cand.id
    child.candidate_count = 1
    work.active_version_id = child.id
    # work 快照回写（人工混音时长为准）
    work.duration_sec = int(duration)
    work.bpm = cand.bpm

    dest = settings.audio_path / work.id / child.id / "candidates" / "A"
    dest.mkdir(parents=True, exist_ok=True)
    from app.synth.mp3_io import encode_mp3
    from app.synth.wav_io import write_wav
    m = dest / "master.wav"
    size = write_wav(m, [left, right], bits=24)
    sha = hashlib.sha256(m.read_bytes()).hexdigest()
    now2 = utc_now_iso()
    db.add(FileRow(work_id=work.id, version_id=child.id, candidate_id=cand.id,
                   kind="master", stem_name=None, name=f"{work.display_code}_{child.version_no}_mixdown.wav",
                   path=str(m.relative_to(settings.audio_path)).replace(chr(92), "/"),
                   mime="audio/wav", bytes=size, duration_sec=duration,
                   sample_rate=sr, sha256=sha, created_at=now2, updated_at=now2))
    p = dest / "preview.mp3"
    size = encode_mp3(p, left, right, bitrate=192)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    db.add(FileRow(work_id=work.id, version_id=child.id, candidate_id=cand.id,
                   kind="preview", stem_name=None, name=f"{work.display_code}_{child.version_no}_mixdown_preview.mp3",
                   path=str(p.relative_to(settings.audio_path)).replace(chr(92), "/"),
                   mime="audio/mpeg", bytes=size, duration_sec=duration,
                   sample_rate=sr, sha256=sha, created_at=now2, updated_at=now2))
    db.flush()
    cand.preview_file_id = db.execute(
        select(FileRow.id).where(FileRow.version_id == child.id,
                                 FileRow.kind == "preview")).scalars().first()
    works_svc.add_event(db, user_id=user.id, action="generate", actor="human",
                                detail={"op": "mixdown", "source_version_id": version.id,
                                        "notes": (notes or "")[:500],
                                        "duration_sec": duration,
                                        "auto_adopted": True},
                                work_id=work.id, version_id=child.id)
    db.commit()
    return {"version": {"id": child.id, "version_no": child.version_no,
                        "source": "mixdown"},
            "work": {"id": work.id, "title": work.title}}
