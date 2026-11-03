"""参考音轨路由（v0.8.1）：octet-stream 上传（零新依赖，无 python-multipart）。

请求体流式读取（超 50MB 即断）；wav 特征分析为 CPU 密集，包进工作线程执行
（2026-10-27：此前 async 端点把分析跑在事件循环上，处理期间全部并发请求被冻结）。
"""
from __future__ import annotations

from functools import partial

from anyio import to_thread
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.core.uploads import read_body_limited
from app.database import get_db
from app.models import User
from app.services import reference as reference_svc
from app.services.reference import MAX_BYTES

router = APIRouter(tags=["reference"])


@router.post("/reference-tracks", status_code=201)
async def create_reference_track(
    request: Request,
    filename: str = Query(min_length=5, max_length=120),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """上传参考音频原件（mp3/wav/m4a）。

    上传即确认权利（ack 语义并入本调用，notice 见响应）；wav 原件同步完成
    特征分析，mp3/m4a 待浏览器解码渲染补传（POST /reference-tracks/{id}/analysis-wav）。
    """
    body = await read_body_limited(
        request, MAX_BYTES,
        "参考音频超过 50MB 上限", "Reference audio exceeds the 50MB limit")
    result = await to_thread.run_sync(
        partial(reference_svc.create_track, db, user, filename=filename, content=body))
    return ok(result, status_code=201)


@router.post("/reference-tracks/{track_id}/analysis-wav")
async def attach_analysis_wav(track_id: str, request: Request,
                              user: User = Depends(get_current_user),
                              db: Session = Depends(get_db)):
    """补传浏览器解码的 mono wav（mp3/m4a 服务端不解码）→ 服务端特征分析。"""
    body = await read_body_limited(
        request, MAX_BYTES,
        "分析音频超过 50MB 上限", "Analysis wav exceeds the 50MB limit")
    return ok(await to_thread.run_sync(
        reference_svc.attach_analysis_wav, db, user, track_id, body))


@router.get("/reference-tracks")
def list_reference_tracks(page: int = Query(default=1, ge=1),
                          page_size: int = Query(default=20, ge=1, le=100),
                          user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    return ok(reference_svc.list_tracks(db, user, page, page_size))


@router.get("/reference-tracks/{track_id}")
def get_reference_track(track_id: str, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    return ok(reference_svc.track_to_dict(reference_svc.get_owned(db, user, track_id)))


@router.delete("/reference-tracks/{track_id}")
def delete_reference_track(track_id: str, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    return ok(reference_svc.delete_track(db, user, track_id))
