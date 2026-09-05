"""哼唱成歌路由（v0.11.0）：录音 → 音高轮廓（0 积分，分析不落库）。"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.services import hum as hum_svc

router = APIRouter(prefix="/hum", tags=["hum"])


@router.post("/analyze")
async def analyze(
    body: bytes = Body(media_type="application/octet-stream"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """哼唱分析：mono wav（PCM16/24/float32，≤8MB ≤60s）→ 音高轮廓。

    响应 hum_melody（[[相对半音, 拍长], ...]）可直接作为 POST /generations 的
    params.hum_melody（本地引擎通道）——引擎保音程关系映射为人声旋律。
    """
    return ok(hum_svc.analyze_hum(body))
