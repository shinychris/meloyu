"""哼唱成歌路由（v0.11.0）：录音 → 音高轮廓（0 积分，分析不落库）。

请求体流式读取（超 8MB 即断）；音高分析为 CPU 密集，包进工作线程执行
（2026-10-27：此前 async 端点把整段 DSP 跑在事件循环上，处理期间全部
并发请求被冻结）。
"""
from __future__ import annotations

from anyio import to_thread
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.core.uploads import read_body_limited
from app.database import get_db
from app.models import User
from app.services import hum as hum_svc
from app.services.hum import MAX_HUM_BYTES

router = APIRouter(prefix="/hum", tags=["hum"])


@router.post("/analyze")
async def analyze(request: Request,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """哼唱分析：mono wav（PCM16/24/float32，≤8MB ≤60s）→ 音高轮廓。

    响应 hum_melody（[[相对半音, 拍长], ...]）可直接作为 POST /generations 的
    params.hum_melody（本地引擎通道）——引擎保音程关系映射为人声旋律。
    """
    body = await read_body_limited(
        request, MAX_HUM_BYTES,
        f"哼唱音频超过 {MAX_HUM_BYTES // 1024 // 1024}MB 上限",
        f"Hum audio exceeds the {MAX_HUM_BYTES // 1024 // 1024}MB limit")
    return ok(await to_thread.run_sync(hum_svc.analyze_hum, body))
