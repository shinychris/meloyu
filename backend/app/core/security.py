"""JWT 签发/校验、bcrypt、get_current_user 依赖（架构 ADR-007：PyJWT + bcrypt）。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
TOKEN_TTL_SEC = 7 * 24 * 3600  # 7 天（契约 §1.2）
BCRYPT_ROUNDS = 12


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
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=TOKEN_TTL_SEC)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """解码并校验 JWT；过期抛 40102，其余无效抛 40101。"""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise err_token_expired() from None
    except jwt.InvalidTokenError:
        raise err_unauthenticated() from None


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
