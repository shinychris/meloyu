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
from app.services.serializers import task_to_dict
from app.synth.editing import derive_op_seed

DERIVED_OPS = ("extend", "variant", "regen_section")
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
                   section: str | None = None, occurrence: int = 1) -> dict:
    """提交派生生成：建子版本 + 任务 + 扣积分，返回 POST /generations 同构响应。"""
    if op not in DERIVED_OPS:
        raise err_validation(tr(f"未知派生操作：{op}", f"Unknown derived operation: {op}"))
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
    schedule_generation(task.id)

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
