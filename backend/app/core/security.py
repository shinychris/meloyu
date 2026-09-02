"""JWT 签发/校验、bcrypt、get_current_user 依赖（架构 ADR-007：PyJWT + bcrypt）。

P1-3（v0.7.0）：access 24h + refresh 30d 轮换（单设备会话语义：新 refresh 覆写
users.refresh_token_hash，旧 refresh 自动失效；登出/改密/重置/注销清空即吊销全部）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import err_token_expired, err_unauthenticated
from app.core.responses import current_request_id
from app.database import get_db
from app.models import User

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_SEC = 24 * 3600          # access 24 小时（契约 §1.2，v0.7.0 由 7 天收紧）
REFRESH_TOKEN_TTL_SEC = 30 * 24 * 3600    # refresh 30 天，轮换式
TOKEN_TTL_SEC = ACCESS_TOKEN_TTL_SEC      # 兼容旧引用（expires_in 等展示口径）
BCRYPT_ROUNDS = 12
RESET_TOKEN_TTL_SEC = 30 * 60             # 找回密码重置令牌 30 分钟


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user.id,
        "plan": user.plan,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ACCESS_TOKEN_TTL_SEC)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def create_reset_token(user: User) -> str:
    """找回密码重置令牌（短效 JWT，typ=reset；仅用于重置流程，不作 API 凭证）。"""
    now = datetime.now(UTC)
    payload = {
        "sub": user.id,
        "typ": "reset",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=RESET_TOKEN_TTL_SEC)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_reset_token(token: str) -> str | None:
    """校验重置令牌；有效返回 user_id，无效/过期/类型不符返回 None。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("typ") != "reset":
        return None
    return payload.get("sub")


# ---- 刷新令牌（随机串 + sha256 复合存储 "<expiry_iso>|<sha256>"，轮换即覆写）----


def _refresh_record(token: str, expires: datetime) -> str:
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    return f"{expires.strftime('%Y-%m-%dT%H:%M:%SZ')}|{digest}"


def issue_refresh_token(user: User) -> tuple[str, int]:
    """生成并挂载刷新令牌（不落库，由调用方 commit）；返回 (明文, ttl 秒)。"""
    token = secrets.token_urlsafe(48)
    expires = datetime.now(UTC) + timedelta(seconds=REFRESH_TOKEN_TTL_SEC)
    user.refresh_token_hash = _refresh_record(token, expires)
    return token, REFRESH_TOKEN_TTL_SEC


def verify_refresh_token(user: User, token: str) -> bool:
    record = user.refresh_token_hash or ""
    try:
        expires_iso, digest = record.split("|", 1)
    except ValueError:
        return False
    if expires_iso <= datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"):
        return False
    return hmac.compare_digest(digest,
                               hashlib.sha256(token.encode("ascii")).hexdigest())


def revoke_refresh_token(user: User) -> None:
    user.refresh_token_hash = None


def decode_access_token(token: str) -> dict:
    """解码并校验 JWT；过期抛 40102，其余无效（含 typ 非 access）抛 40101。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise err_token_expired() from None
    except jwt.InvalidTokenError:
        raise err_unauthenticated() from None
    # typ 缺省视为 access（升级前签发的旧 7 天 token 兼容）；reset 等专用令牌禁作凭证
    if payload.get("typ") not in ("access", None):
        raise err_unauthenticated()
    return payload


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    return token or None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _extract_bearer(request)
    if not token:
        raise err_unauthenticated()
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise err_unauthenticated()
    request.state.request_id = current_request_id()
    return user


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    """可选鉴权：无 Authorization 头返回 None（供 ?st= 流地址端点）；
    有头但无效仍然抛 40101/40102。"""
    token = _extract_bearer(request)
    if not token:
        return None
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise err_unauthenticated()
    return user


# ---- 短时流地址签名（契约 §9.4：<audio> 标签无法携带 Authorization 头）----


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def make_stream_token(file_id: str, user_id: str, ttl: int = 900) -> str:
    body = _b64url(json.dumps(
        {"f": file_id, "u": user_id, "e": int(datetime.now(UTC).timestamp()) + ttl},
        separators=(",", ":"),
    ).encode("utf-8"))
    sig = _b64url(hmac.new(settings.jwt_secret.encode("utf-8"), body.encode("ascii"),
                           hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_stream_token(token: str) -> dict | None:
    """校验 st 签名；返回 {f,u} 或 None（无效/过期）。"""
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        return None
    expect = _b64url(hmac.new(settings.jwt_secret.encode("utf-8"), body.encode("ascii"),
                              hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        payload = json.loads(_b64url_decode(body))
        if int(payload.get("e", 0)) < int(datetime.now(UTC).timestamp()):
            return None
        return {"f": payload.get("f"), "u": payload.get("u")}
    except Exception:
        return None
