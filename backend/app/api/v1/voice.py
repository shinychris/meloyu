"""人声音色档案路由（v0.8.2）：octet-stream 采样上传（与参考音频同协议）。

采样请求体流式读取（超 20MB 即断）+ 特征提取包进工作线程（2026-10-27，
与 hum/reference 上传通道同口径——避免阻塞事件循环）。
"""
from __future__ import annotations

from anyio import to_thread
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.core.uploads import read_body_limited
from app.database import get_db
from app.models import User
from app.services import voice as voice_svc
from app.services.voice import MAX_SAMPLE_BYTES

router = APIRouter(tags=["voice"])


@router.post("/voice-profiles", status_code=201)
def enroll_voice_profile(
    name: str = Query(min_length=1, max_length=60),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """注册音色档案（步骤0）：服务端下发随机短语1，客户端录音回传 samples?step=1。"""
    return ok(voice_svc.enroll(db, user, name), status_code=201)


@router.post("/voice-profiles/{profile_id}/samples")
async def submit_voice_sample(
    profile_id: str, request: Request,
    step: int = Query(ge=1, le=2),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """上传朗读采样（mono wav，浏览器解码渲染）。

    step=1 存样本并下发短语2；step=2 双样本同人校验 → verified（timbre 随响应返回）。
    """
    body = await read_body_limited(
        request, MAX_SAMPLE_BYTES,
        "采样超过 20MB 上限", "Sample exceeds the 20MB limit")
    return ok(await to_thread.run_sync(
        voice_svc.submit_sample, db, user, profile_id, step, body))


@router.get("/voice-profiles")
def list_voice_profiles(user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    return ok(voice_svc.list_profiles(db, user))


@router.get("/voice-profiles/{profile_id}")
def get_voice_profile(profile_id: str, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    return ok(voice_svc.profile_to_dict(voice_svc.get_owned(db, user, profile_id)))


@router.delete("/voice-profiles/{profile_id}")
def delete_voice_profile(profile_id: str, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """删除=吊销：档案与采样清除（仅本人可操作）。"""
    return ok(voice_svc.delete_profile(db, user, profile_id))
