"""订阅路由（2 接口）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.auth import SwitchPlanRequest
from app.services import billing as billing_svc

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("/plans")
def plans(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(billing_svc.list_plans(db, user))


@router.post("/switch")
def switch(body: SwitchPlanRequest, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    return ok(billing_svc.switch_plan(db, user, body.plan))
