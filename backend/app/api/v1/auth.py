"""auth 路由（v0.7.0：3 → 10 接口——刷新/登出/验证码/找回重置/改密/注销/导出）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SendCodeRequest,
)
from app.services import auth as auth_svc

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    return ok(auth_svc.register(db, body.email, body.password, body.nickname,
                                body.code), status_code=201)


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    return ok(auth_svc.login(db, body.email, body.password))


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(auth_svc.me(db, user))


@router.post("/refresh")
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    return ok(auth_svc.refresh(db, body.refresh_token))


@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(auth_svc.logout(db, user))


@router.post("/send-code")
def send_code(body: SendCodeRequest, db: Session = Depends(get_db)):
    from app.services import mail as mail_svc
    mail_svc.send_verification_code(body.email)
    return ok({"ok": True})


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    return ok(auth_svc.forgot_password(db, body.email))


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    return ok(auth_svc.reset_password(db, body.token, body.new_password))


@router.post("/change-password")
def change_password(body: ChangePasswordRequest,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(auth_svc.change_password(db, user, body.old_password, body.new_password))


@router.post("/delete-account")
def delete_account(body: DeleteAccountRequest,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(auth_svc.delete_account(db, user, body.password))


@router.get("/export-data")
def export_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    filename, payload = auth_svc.export_data(db, user)
    return Response(content=payload, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
