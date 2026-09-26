"""开放 API（FR-19，v0.8.2）：
- /api-keys（站内 JWT）：密钥签发（完整 key 仅返回一次）/列表/吊销
- /public/*（密钥鉴权）：文本生歌/任务查询/作品列表/文件下载

按量计费：生成经 submit_generation 走账号积分账本（模型单价与站内一致）；
任务留痕 request_payload.via="api_key"（key 名一并留痕，审计可溯）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import audio_files as af
from app.core.responses import ok
from app.core.security import get_current_user, get_user_from_api_key
from app.database import get_db
from app.models import User
from app.schemas.auth import GenerationRequest
from app.services import api_keys as keys_svc
from app.services import generation as gen_svc
from app.services import works as works_svc
from app.services.serializers import task_to_dict

router = APIRouter(tags=["openapi"])
keys_router = APIRouter(prefix="/api-keys", tags=["openapi"])


# ---- 密钥管理（站内 JWT） ----

class IssueKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@keys_router.post("", status_code=201)
def issue_key(body: IssueKeyRequest, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    return ok(keys_svc.issue_key(db, user, body.name), status_code=201)


@keys_router.get("")
def list_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(keys_svc.list_keys(db, user))


@keys_router.delete("/{key_id}")
def revoke_key(key_id: str, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    return ok(keys_svc.revoke_key(db, user, key_id))


# ---- 公开 API（密钥鉴权） ----

@router.post("/public/generations", status_code=201)
def public_generate(body: GenerationRequest, request: Request,
                    auth: tuple[User, object] = Depends(get_user_from_api_key),
                    db: Session = Depends(get_db)):
    """文本生歌（与站内 /generations 同构：mode/simple_prompt 或 style_prompt+lyrics/params）。

    按量计费：提交即扣账号积分（v1_pro=12 / v1_fast=6），失败自动退款；轮询
    GET /public/tasks/{id} 至 succeeded 后经 result.files 下载。
    """
    user, key_row = auth
    out = gen_svc.submit_generation(db, user, body.payload())
    row = _task_row(db, out["task"]["id"])
    # 留痕：本任务经 API 密钥发起（审计可溯到 key；计费已随 submit 扣账号积分）
    snap = dict(row.request_payload or {})
    snap["via"] = {"source": "api_key", "key_id": key_row.id, "key_name": key_row.name}
    row.request_payload = snap
    db.commit()
    out["task"] = task_to_dict(_task_row(db, out["task"]["id"]))
    out["poll"] = f"/api/v1/public/tasks/{out['task']['id']}"
    return ok(out, status_code=201)


def _task_row(db: Session, task_id: str):
    from sqlalchemy.orm import Session as _S  # noqa: F401

    from app.models import Task
    return db.get(Task, task_id)


@router.get("/public/tasks/{task_id}")
def public_task(task_id: str,
                auth: tuple[User, object] = Depends(get_user_from_api_key),
                db: Session = Depends(get_db)):
    user, _ = auth
    task = gen_svc.get_task_owned(db, task_id, user)
    data = task_to_dict(task)
    if task.status == "succeeded" and task.result:
        # 生成任务 result=candidates（各含 files/preview_file_id）；导出任务 result=files
        file_ids: list[str] = []
        for f in (task.result.get("files") or []):
            file_ids.append(f["file_id"])
        for c in (task.result.get("candidates") or []):
            file_ids.extend(f["file_id"] for f in (c.get("files") or []))
            if c.get("preview_file_id"):
                file_ids.append(c["preview_file_id"])
        if file_ids:
            data["downloads"] = [
                f"/api/v1/public/files/{fid}/download" for fid in dict.fromkeys(file_ids)
            ]
    return ok(data)


@router.get("/public/works")
def public_works(page: int = Query(default=1, ge=1),
                 page_size: int = Query(default=20, ge=1, le=100),
                 auth: tuple[User, object] = Depends(get_user_from_api_key),
                 db: Session = Depends(get_db)):
    user, _ = auth
    return ok(works_svc.list_works(db, user, q=None, tag=None, favorite=None,
                                   status="active", sort="updated_at", order="desc",
                                   page=page, page_size=page_size))


@router.get("/public/files/{file_id}/download")
def public_download(file_id: str, request: Request,
                    auth: tuple[User, object] = Depends(get_user_from_api_key),
                    db: Session = Depends(get_db)):
    user, _ = auth
    f = af.resolve_file(db, file_id)
    af.check_owner(db, f, user)
    return af.file_stream_response(request, f, download=True)
