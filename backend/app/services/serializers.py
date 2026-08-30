"""契约资源对象的组装（schemas 层白名单式输出，模型 to_dict 只出扁平列）。"""
from __future__ import annotations

from app.models import Candidate, EditEvent, File, Task, User, Version, Work


def user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "nickname": u.nickname,
        "plan": u.plan,
        "credits": {
            "balance": u.credit_balance,
            "monthly_grant": u.credit_monthly_grant,
            "carried_over": u.credit_carried_over,
            "next_grant_at": u.credit_next_grant_at,
        },
        "created_at": u.created_at,
    }


def file_ref(f: File) -> dict:
    return {
        "file_id": f.id,
        "kind": f.kind,
        "stem_name": f.stem_name,
        "name": f.name,
        "mime": f.mime,
        "bytes": f.bytes,
        "duration_sec": f.duration_sec,
    }


def task_to_dict(t: Task) -> dict:
    error = None
    if t.error_code is not None:
        error = {"code": t.error_code, "message": t.error_message or ""}
    return {
        "id": t.id,
        "type": t.type,
        "status": t.status,
        "format": t.format,
        "progress": t.progress,
        "stage_key": t.stage_key,
        "stage_label": t.stage_label,
        "error": error,
        "work_id": t.work_id,
        "version_id": t.version_id,
        "result": t.result,
        "created_at": t.created_at,
        "started_at": t.started_at,
        "finished_at": t.finished_at,
    }


def candidate_to_dict(c: Candidate, files: list[File] | None = None) -> dict:
    file_list = files if files is not None else list(c.files)
    kind_order = {"preview": 0, "master": 1, "stem": 2}
    file_list = sorted(file_list, key=lambda f: (kind_order.get(f.kind, 9), f.stem_name or ""))
    return {
        "id": c.id,
        "version_id": c.version_id,
        "label": c.label,
        "adopted": c.adopted,
        "seed": c.seed,
        "quality_score": c.quality_score,
        "duration_sec": c.duration_sec,
        "bpm": c.bpm,
        "key": {"tonic": c.key_tonic, "mode": c.key_mode},
        "time_signature": c.time_signature,
        "vocal": c.vocal,
        "language": c.language,
        "style_tags": c.style_tags or [],
        "structure": c.structure or [],
        "applied_negative": c.applied_negative or [],
        "files": [file_ref(f) for f in file_list],
        "created_at": c.created_at,
    }


def work_to_dict(w: Work) -> dict:
    return {
        "id": w.id,
        "display_code": w.display_code,
        "title": w.title,
        "status": w.status,
        "favorite": w.favorite,
        "tags": w.tags or [],
        "cover_color": w.cover_color,
        "bpm": w.bpm,
        "key": {"tonic": w.key_tonic, "mode": w.key_mode},
        "duration_sec": w.duration_sec,
        "model": w.model,
        "version_count": w.version_count,
        "active_version_id": w.active_version_id,
        "preview_file_id": w.preview_file_id,
        "created_at": w.created_at,
        "updated_at": w.updated_at,
        "trashed_at": w.trashed_at,
    }


def version_to_dict(v: Version) -> dict:
    return {
        "id": v.id,
        "work_id": v.work_id,
        "parent_version_id": v.parent_version_id,
        "version_no": v.version_no,
        "source": v.source,
        "active_candidate_id": v.active_candidate_id,
        "candidate_count": v.candidate_count,
        "params": v.params or {},
        "lyrics": v.lyrics or "",
        "created_at": v.created_at,
    }


def event_to_dict(e: EditEvent) -> dict:
    return {
        "id": e.id,
        "work_id": e.work_id,
        "version_id": e.version_id,
        "task_id": (e.detail or {}).get("task_id"),
        "action": e.action,
        "actor": e.actor,
        "detail": e.detail or {},
        "created_at": e.created_at,
    }
