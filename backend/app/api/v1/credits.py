"""积分路由（2 接口）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.services import credits as credits_svc

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("/balance")
def balance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    credits_svc.lazy_monthly_grant(db, user)
    db.commit()
    db.refresh(user)
    return ok(credits_svc.balance_dict(user))


@router.get("/transactions")
def transactions(page: int = Query(default=1, ge=1),
                 page_size: int = Query(default=20, ge=1, le=100),
                 user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return ok(credits_svc.list_transactions(db, user.id, page, min(page_size, 100)))
