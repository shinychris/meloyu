"""License 路由（3 接口，B2：状态/激活/解除激活）。

enterprise 形态（2026-10-27）：激活/解除是站点级治理操作（整租授权状态），
普通成员不得触碰——解除=破坏性 DoS，激活还牵动档位语义，两端口收敛 admin；
desktop 单机形态维持现状（本地档案即管理员，无第二用户）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import err_forbidden
from app.core.i18n import tr
from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.license import ActivateLicenseRequest, OnlineActivateRequest
from app.services import license as license_svc

router = APIRouter(prefix="/licenses", tags=["licenses"])


def require_mode_admin(user: User = Depends(get_current_user)) -> User:
    """enterprise 形态下激活/解除需管理员（站点级授权治理操作）。"""
    if settings.app_mode == "enterprise" and not user.is_admin:
        raise err_forbidden(tr(
            "企业版 License 激活/解除需管理员权限（站点级授权操作）",
            "License activation/deactivation requires administrator rights "
            "in enterprise mode (site-wide licensing operation)"))
    return user


@router.get("/status")
def status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(license_svc.status_dict(db))


@router.post("/activate")
def activate(body: ActivateLicenseRequest,
             user: User = Depends(require_mode_admin),
             db: Session = Depends(get_db)):
    return ok(license_svc.activate(db, body.license_key, user=user))


@router.post("/activate-online")
def activate_online(body: OnlineActivateRequest,
                    user: User = Depends(require_mode_admin),
                    db: Session = Depends(get_db)):
    return ok(license_svc.activate_online(db, user, body.account, body.code))


@router.post("/deactivate")
def deactivate(user: User = Depends(require_mode_admin), db: Session = Depends(get_db)):
    return ok(license_svc.deactivate(db))
