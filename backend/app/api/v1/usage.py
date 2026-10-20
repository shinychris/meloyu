"""用量统计路由（1 接口，v0.17.0）：用户自定义 API 调用的统计与分析。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.services import usage as usage_svc

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/stats")
def stats(days: int = Query(default=30, ge=1, le=180),
          user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    """按天/按引擎通道聚合生成用量（license 模式=纯计量，无扣减语义）。"""
    return ok(usage_svc.stats_dict(db, user, days))
