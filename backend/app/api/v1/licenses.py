"""License 路由（3 接口，B2：状态/激活/解除激活）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.license import ActivateLicenseRequest, OnlineActivateRequest
from app.services import license as license_svc

router = APIRouter(prefix="/licenses", tags=["licenses"])


@router.get("/status")
def status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(license_svc.status_dict(db))


@router.post("/activate")
def activate(body: ActivateLicenseRequest,
             user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    return ok(license_svc.activate(db, body.license_key, user=user))


@router.post("/activate-online")
def activate_online(body: OnlineActivateRequest,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    return ok(license_svc.activate_online(db, user, body.account, body.code))


@router.post("/deactivate")
def deactivate(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(license_svc.deactivate(db))
