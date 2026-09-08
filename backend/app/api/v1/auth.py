"""auth 路由（v0.7.0：3 → 10 接口——刷新/登出/验证码/找回重置/改密/注销/导出）。

安审计 M-1/M-2（2026-09-09）：refresh token 改经 HttpOnly+SameSite=Strict
Cookie 下发（Path 限定 /api/v1/auth），不再出现在响应体——localStorage 中的
refresh 可被任意同源 JS 窃取，XSS 后即 30 天凭据失陷；HttpOnly 域内 JS 不可
读，XSS 至多窃取 24h access。/auth/refresh 兼容从 Cookie 或请求体取令牌
（旧客户端/脚本过渡期），登出同时清 Cookie。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import API_PREFIX, settings
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

REFRESH_COOKIE = "meloyu_refresh"


def _is_https(request: Request) -> bool:
    scheme = request.url.scheme
    if settings.trust_proxy:
        scheme = request.headers.get("x-forwarded-proto", "").strip() or scheme
    return scheme == "https"


def _set_refresh_cookie(response: Response, request: Request,
                        token: str, ttl: int) -> None:
    response.set_cookie(
        REFRESH_COOKIE, token, max_age=ttl, httponly=True, samesite="strict",
        path=f"{API_PREFIX}/auth", secure=_is_https(request))


@router.post("/register", status_code=201)
def register(body: RegisterRequest, request: Request,
             db: Session = Depends(get_db)):
    out, refresh, ttl = auth_svc.register(db, body.email, body.password,
                                          body.nickname, body.code)
    resp = ok(out, status_code=201)
    _set_refresh_cookie(resp, request, refresh, ttl)
    return resp


@router.post("/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    out, refresh, ttl = auth_svc.login(db, body.email, body.password)
    resp = ok(out)
    _set_refresh_cookie(resp, request, refresh, ttl)
    return resp


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(auth_svc.me(db, user))


@router.post("/refresh")
def refresh(body: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    # Cookie 优先（HttpOnly 主通道）；请求体保留兼容旧客户端/脚本
    token = request.cookies.get(REFRESH_COOKIE) or body.refresh_token
    out, new_refresh, ttl = auth_svc.refresh(db, token)
    resp = ok(out)
    _set_refresh_cookie(resp, request, new_refresh, ttl)
    return resp


@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    resp = ok(auth_svc.logout(db, user))
    resp.delete_cookie(REFRESH_COOKIE, path=f"{API_PREFIX}/auth")
    return resp


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
