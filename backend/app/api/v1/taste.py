"""我的口味（V2-b，v0.9.1）：画像读取与重建（建议值语义，无模型训练）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.services import taste as taste_svc

router = APIRouter(prefix="/taste", tags=["taste"])


@router.get("")
def get_taste(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """画像读取（首次访问懒构建）。"""
    return ok(taste_svc.get(db, user))


@router.post("/rebuild")
def rebuild_taste(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """重建画像（扫描本人作品库；作品变更后手动刷新）。"""
    return ok(taste_svc.rebuild(db, user))
