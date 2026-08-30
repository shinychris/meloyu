"""生成编排：扣积分→建任务→线程池执行→进度回写→候选落库→失败退款。

任务状态机与线程池见 core/tasks.py；本模块只做业务编排。
"""
from __future__ import annotations

import time
from datetime import UTC
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import GENERATION_TASK_TIMEOUT_SEC, MODEL_CREDIT_COST, settings
from app.core.errors import (
    err_conflict,
    err_forbidden,
    err_not_found,
    err_payment_required,
    err_sensitive,
)
from app.core.logging import logger
from app.core.seed import cover_color_for_seed, derive_seed
from app.database import SessionLocal
from app.models import Candidate, File, Task, User, Version, Work
from app.models.base import utc_now_iso
from app.providers.base import STAGE_LABELS, SynthCancelled, get_music_provider
from app.providers.lyrics_local import LocalLyricsProvider, check_sensitive
from app.services import works as works_svc
from app.services.serializers import candidate_to_dict, task_to_dict
from app.synth.ir import SongRequest

_lyrics_provider = LocalLyricsProvider()


# ---------- 提交 ----------

def expand_simple_prompt(simple_prompt: str) -> str:
    """simple 模式：一句话扩写为 style_prompt（规则引擎）。"""
    base = (simple_prompt or "").strip().rstrip("。，,.")
    return f"{base}，流行编曲，钢琴与弦乐铺底，人声旋律清晰，情绪自然流动"


def resolve_generation_request(payload: dict) -> dict:
    """规范化请求：simple 扩写、歌词自动生成、simplified 减半、seed 派生。"""
    mode = payload.get("mode", "simple")
    simplified = bool(payload.get("simplified", False))
    params = dict(payload.get("params") or {})

    if mode == "simple":
        style_prompt = expand_simple_prompt(payload.get("simple_prompt") or "")
    else:
        style_prompt = payload.get("style_prompt") or ""
    if simplified and style_prompt:
        parts = [p for p in style_prompt.replace("，", ",").split(",") if p.strip()]
        style_prompt = "，".join(p.strip() for p in parts[: max(1, len(parts) // 2)])

    lyrics = payload.get("lyrics") or ""
    vocal = params.get("vocal", "female_air")
    if not lyrics and vocal != "instrumental":
        theme = payload.get("simple_prompt") or style_prompt[:60]
        gen = _lyrics_provider.generate(theme=theme, style_hint=style_prompt[:80],
                                        mood=None, language=params.get("language", "zh"))
        lyrics = gen["lyrics"]

    full_params = {
        "mode": mode, "style_prompt": style_prompt,
        "negative_prompt": payload.get("negative_prompt") or "",
        "model": payload.get("model") or "v1_pro",
        "bpm": params.get("bpm", 90),
        "key": params.get("key", {"tonic": "A", "mode": "minor"}),
        "time_signature": params.get("time_signature", "4/4"),
        "duration_sec": params.get("duration_sec", 210),
        "vocal": vocal, "language": params.get("language", "zh"),
        "instrument_density": params.get("instrument_density", 65),
    }
    seed = payload.get("seed")
    if seed is None:
        seed = derive_seed(full_params, settings.server_nonce)
    return {"style_prompt": style_prompt, "lyrics": lyrics, "params": full_params,
            "seed": int(seed) & 0xFFFFFFFF}


def check_generation_content(payload: dict) -> None:
    text = " ".join(filter(None, [
        payload.get("style_prompt") or "", payload.get("simple_prompt") or "",
        payload.get("lyrics") or "", payload.get("negative_prompt") or "",
    ]))
    if check_sensitive(text):
        raise err_sensitive()


def _check_free_daily_limit(db: Session, user: User) -> None:
    if user.plan != "free":
        return
    from datetime import datetime, timedelta
    # 自然日按 UTC+8：当日 00:00 (UTC+8) = 前一日 16:00 UTC
    now_cn = datetime.now(UTC) + timedelta(hours=8)
    day_start_utc = (now_cn.replace(hour=0, minute=0, second=0, microsecond=0)
                     - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    count = db.execute(
        select(func.count()).select_from(Task).where(
            Task.user_id == user.id, Task.type == "generation",
            Task.created_at >= day_start_utc)
    ).scalar_one()
    if count >= 5:
        raise err_payment_required("今日免费生成次数已用完")


def submit_generation(db: Session, user: User, payload: dict) -> dict:
    check_generation_content(payload)
    _check_free_daily_limit(db, user)

    resolved = resolve_generation_request(payload)
    params = resolved["params"]
    cost = MODEL_CREDIT_COST.get(params["model"], 12)

    # work / version
    work_id = payload.get("work_id")
    parent_version_id = payload.get("parent_version_id")
    now = utc_now_iso()
    if work_id:
        work = works_svc.get_work_row(db, work_id, user)
    else:
        title = _derive_title(payload, params)
        work = Work(user_id=user.id, display_code=works_svc.new_display_code(db),
                    title=title, status="active", favorite=False, tags=[],
                    bpm=params["bpm"],
                    key_tonic=params["key"]["tonic"], key_mode=params["key"]["mode"],
                    duration_sec=params["duration_sec"], model=params["model"],
                    cover_color=cover_color_for_seed(resolved["seed"]),
                    created_at=now, updated_at=now)
        db.add(work)
        db.flush()
    version_no = f"v{work.version_count + 1}"
    if parent_version_id:
        parent = db.get(Version, parent_version_id)
        if not parent or parent.work_id != work.id:
            raise err_not_found("父版本不存在")
    else:
        latest = db.execute(select(Version).where(Version.work_id == work.id)
                            .order_by(Version.created_at.desc(), Version.id.desc())
                            .limit(1)).scalars().first()
        parent_version_id = latest.id if latest else None
    version = Version(work_id=work.id, parent_version_id=parent_version_id,
                      version_no=version_no, source="generate", candidate_count=0,
                      params=params, lyrics=resolved["lyrics"], created_at=now,
                      updated_at=now)
    db.add(version)
    db.flush()
    work.version_count += 1
    work.updated_at = now

    request_snapshot = {
        "mode": payload.get("mode"), "simple_prompt": payload.get("simple_prompt"),
        "style_prompt": payload.get("style_prompt"), "lyrics": payload.get("lyrics"),
        "negative_prompt": payload.get("negative_prompt"),
        "model": payload.get("model"), "work_id": work_id,
        "parent_version_id": parent_version_id,
        "simplified": bool(payload.get("simplified", False)),
        "seed": payload.get("seed"), "params": payload.get("params"),
        "_resolved": resolved,
    }
    task = Task(user_id=user.id, type="generation", status="queued", progress=0,
                stage_key="queued", stage_label="排队中", work_id=work.id,
                version_id=version.id, provider="localsynth", seed=resolved["seed"],
                cost_credits=cost, request_payload=request_snapshot,
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


def _derive_title(payload: dict, params: dict) -> str:
    if payload.get("mode") == "simple" and payload.get("simple_prompt"):
        return payload["simple_prompt"][:12]
    if params.get("style_prompt"):
        return params["style_prompt"][:12]
    return "未命名作品"


# ---------- 执行（线程池内）----------

def execute_generation(task_id: str) -> None:
    t_start = time.monotonic()
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if task is None or task.status != "queued":
            return
        task.status = "running"
        task.started_at = utc_now_iso()
        task.updated_at = utc_now_iso()
        db.commit()
        user_id = task.user_id

    try:
        payload_row = task.request_payload or {}
        resolved = payload_row.get("_resolved") or {}
        params = resolved["params"]
        req = SongRequest(
            style_prompt=params["style_prompt"], negative_prompt=params["negative_prompt"],
            model=params["model"], lyrics=resolved.get("lyrics") or "",
            bpm=params["bpm"], tonic=params["key"]["tonic"], mode=params["key"]["mode"],
            time_signature=params["time_signature"], duration_sec=params["duration_sec"],
            vocal=params["vocal"], language=params["language"],
            instrument_density=params["instrument_density"], seed=resolved["seed"],
        )
        dest = settings.audio_path / task.work_id / task.version_id
        provider = get_music_provider()

        def progress(stage_key: str, pct: int, label: str) -> None:
            if time.monotonic() - t_start > GENERATION_TASK_TIMEOUT_SEC:
                raise TimeoutError(f"超过 {GENERATION_TASK_TIMEOUT_SEC}s 熔断")
            _write_progress(task_id, stage_key, pct, label)

        def should_cancel() -> bool:
            with SessionLocal() as db2:
                t = db2.get(Task, task_id)
                return bool(t and t.cancel_requested)

        output = provider.generate(req, progress, should_cancel, str(dest))

        with SessionLocal() as db:
            _persist_success(db, task_id, user_id, output)
        logger.info(f"generation {task_id} done in {time.monotonic() - t_start:.1f}s")
    except SynthCancelled:
        with SessionLocal() as db:
            _finish_task(db, task_id, "canceled", None, None)
            _refund(db, task_id)
            db.commit()
    except TimeoutError as e:
        with SessionLocal() as db:
            _finish_task(db, task_id, "failed", 50002, f"生成失败：渲染超时 {e}")
            _refund(db, task_id)
            db.commit()
    except Exception as e:  # noqa: BLE001 —— 任务级兜底，退款 + 50002
        logger.exception(f"generation {task_id} failed: {e}")
        with SessionLocal() as db:
            _finish_task(db, task_id, "failed", 50002, f"生成失败：{type(e).__name__} {e}")
            _refund(db, task_id)
            db.commit()


def _write_progress(task_id: str, stage_key: str, pct: int, label: str) -> None:
    with SessionLocal() as db:
        t = db.get(Task, task_id)
        if t is None or t.status != "running":
            return
        if abs(pct - t.progress) < 2 and stage_key == t.stage_key:
            return
        t.progress = max(0, min(100, pct))
        t.stage_key = stage_key
        t.stage_label = label
        t.updated_at = utc_now_iso()
        db.commit()


def _persist_success(db: Session, task_id: str, user_id: str, output) -> None:
    task = db.get(Task, task_id)
    if task is None or task.status not in ("running", "queued"):
        return
    work = db.get(Work, task.work_id)
    version = db.get(Version, task.version_id)
    now = utc_now_iso()
    result_candidates = []
    for art in output.candidates:
        cand = Candidate(
            version_id=version.id, label=art.label, adopted=False, seed=art.seed,
            quality_score=art.quality_score, duration_sec=int(round(art.duration_sec)),
            bpm=art.bpm, key_tonic=art.tonic, key_mode=art.mode,
            time_signature=art.time_signature, vocal=art.vocal, language=art.language,
            style_tags=art.style_tags, structure=art.structure,
            applied_negative=output.applied_negative, created_at=now, updated_at=now,
        )
        db.add(cand)
        db.flush()
        for fmeta in art.files:
            db.add(File(
                work_id=work.id, version_id=version.id, candidate_id=cand.id,
                kind=fmeta["kind"], stem_name=fmeta.get("stem_name"),
                name=_display_filename(work.display_code, version.version_no, art.label,
                                       fmeta["kind"], fmeta.get("stem_name"),
                                       Path(fmeta["relpath"]).suffix),
                path=f"{work.id}/{version.id}/{fmeta['relpath']}",
                mime=fmeta["mime"], bytes=fmeta["bytes"],
                duration_sec=fmeta.get("duration_sec"), sample_rate=fmeta.get("sample_rate"),
                sha256=fmeta["sha256"], created_at=now, updated_at=now,
            ))
        preview = next((f for f in art.files if f["kind"] == "preview"), None)
        result_candidates.append({
            "id": cand.id, "label": art.label, "quality_score": art.quality_score,
            "duration_sec": int(round(art.duration_sec)),
            "preview_file_id": None,  # 占位，flush 后回填
            "_preview_relpath": preview["relpath"] if preview else None,
        })
    # 回填 preview_file_id
    for rc, _art in zip(result_candidates, output.candidates, strict=False):
        if rc["_preview_relpath"]:
            row = db.execute(select(File).where(
                File.work_id == work.id, File.version_id == version.id,
                File.path == f"{work.id}/{version.id}/{rc['_preview_relpath']}")
            ).scalars().first()
            if row:
                rc["preview_file_id"] = row.id
        rc.pop("_preview_relpath", None)

    version.candidate_count = len(output.candidates)
    version.inferred_structure = bool(output.inferred_structure)
    if version.active_candidate_id is None and result_candidates:
        pass  # 不自动采用，等待用户 adopt（契约语义）
    works_svc.add_event(db, user_id=user_id, action="generate", actor="ai",
                        detail={"task_id": task.id, "provider": "localsynth",
                                "candidates": [rc["label"] for rc in result_candidates]},
                        work_id=work.id, version_id=version.id)
    task.status = "succeeded"
    task.progress = 100
    task.stage_key = "done"
    task.stage_label = STAGE_LABELS["done"][0]
    task.result = {"candidates": result_candidates}
    task.finished_at = now
    task.updated_at = now
    work.updated_at = now
    db.commit()


def _display_filename(display_code: str, version_no: str, label: str, kind: str,
                      stem_name: str | None, ext: str) -> str:
    ext = ext.lstrip(".")
    if kind == "stem":
        return f"{display_code}_{version_no}_{label}_{kind}_{stem_name}.{ext}"
    if kind in ("preview", "master"):
        return f"{display_code}_{version_no}_{label}_{kind}.{ext}"
    return f"{display_code}_{version_no}_{kind}.{ext}"


def _finish_task(db: Session, task_id: str, status: str, error_code: int | None,
                 error_message: str | None) -> None:
    t = db.get(Task, task_id)
    if t is None or t.status in ("succeeded", "failed", "canceled"):
        return
    t.status = status
    t.error_code = error_code
    t.error_message = error_message
    t.finished_at = utc_now_iso()
    t.updated_at = utc_now_iso()
    db.flush()  # 不单独 commit：终态与退款由调用方在同一事务内一次提交


def _refund(db: Session, task_id: str) -> None:
    t = db.get(Task, task_id)
    if t is None or t.cost_credits <= 0:
        return
    user = db.get(User, t.user_id)
    if user is None:
        return
    from app.services.credits import refund
    refund(db, user.id, t.cost_credits, t.id)


# ---------- 查询 / 取消 ----------

def get_task_owned(db: Session, task_id: str, user: User) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise err_not_found("任务不存在")
    if task.user_id != user.id:
        raise err_forbidden()
    return task


def list_tasks(db: Session, user: User, *, type_: str | None, status: str | None,
               work_id: str | None, page: int, page_size: int) -> dict:
    conds = [Task.user_id == user.id]
    if type_:
        conds.append(Task.type == type_)
    if status:
        conds.append(Task.status == status)
    if work_id:
        conds.append(Task.work_id == work_id)
    base = select(Task).where(*conds)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(base.order_by(Task.created_at.desc(), Task.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).scalars().all()
    from app.services.credits import paginate_meta
    return paginate_meta([task_to_dict(t) for t in rows], total, page, page_size)


def cancel_task(db: Session, user: User, task_id: str) -> dict:
    task = get_task_owned(db, task_id, user)
    if task.status in ("succeeded", "failed", "canceled"):
        raise err_conflict("任务已结束，无法取消")
    if task.type == "export":
        raise err_conflict("导出任务不支持取消")
    if task.status == "queued":
        task.status = "canceled"
        task.finished_at = utc_now_iso()
        task.updated_at = utc_now_iso()
        _refund(db, task.id)
        db.commit()  # 终态与退款同事务提交
        db.refresh(task)
        return task_to_dict(task)
    # running：置取消标志，渲染循环在阶段边界到达
    task.cancel_requested = True
    task.stage_label = "正在取消…"
    task.updated_at = utc_now_iso()
    db.commit()
    db.refresh(task)
    return task_to_dict(task)


# ---------- 候选 ----------

def list_candidates(db: Session, version_id: str, user: User) -> dict:
    version = works_svc.get_version_owned(db, version_id, user)
    rows = db.execute(select(Candidate).where(Candidate.version_id == version.id)
                      .order_by(Candidate.label.asc())).scalars().all()
    items = [candidate_to_dict(c) for c in rows]
    return {"items": items, "inferred_structure": bool(version.inferred_structure)}


def get_candidate_owned(db: Session, candidate_id: str, user: User) -> Candidate:
    cand = db.get(Candidate, candidate_id)
    if not cand:
        raise err_not_found("候选不存在")
    works_svc.get_version_owned(db, cand.version_id, user)  # 归属校验
    return cand


def adopt_candidate(db: Session, candidate_id: str, user: User) -> dict:
    from app.services.serializers import version_to_dict
    cand = get_candidate_owned(db, candidate_id, user)
    version = db.get(Version, cand.version_id)
    if version.active_candidate_id == cand.id:
        raise err_conflict("该候选已是活跃候选")
    # 同版本其他候选置 false
    others = db.execute(select(Candidate).where(Candidate.version_id == version.id)).scalars()
    for c in others:
        c.adopted = (c.id == cand.id)
    version.active_candidate_id = cand.id
    work = db.get(Work, version.work_id)
    work.bpm = cand.bpm
    work.key_tonic = cand.key_tonic
    work.key_mode = cand.key_mode
    work.duration_sec = cand.duration_sec
    work.model = version.params.get("model", work.model)
    work.active_version_id = version.id
    # 回写 preview_file_id：该候选的 preview 文件
    preview = db.execute(select(File).where(File.candidate_id == cand.id,
                                            File.kind == "preview")).scalars().first()
    if preview:
        work.preview_file_id = preview.id
    work.updated_at = utc_now_iso()
    works_svc.add_event(db, user_id=user.id, action="adopt", actor="human",
                        detail={"candidate_id": cand.id, "label": cand.label},
                        work_id=work.id, version_id=version.id)
    db.commit()
    db.refresh(version)
    return version_to_dict(version)
