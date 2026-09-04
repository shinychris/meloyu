"""开放 API 密钥（FR-19，v0.8.2）：key 签发/吊销/鉴权。

口径：key 仅在创建时完整返回一次（落库只存 sha256）；按量计费=复用账号积分账本
（生成按模型单价扣减，与站内一致）；商用授权随账号档位×通道许可走证书（key 即账号
身份的机器代理，PRD「商用授权绑定密钥」落地为：任务留痕 via=api_key + 证书同源）。
"""
from __future__ import annotations

import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import err_conflict, err_not_found, err_validation
from app.core.i18n import tr
from app.models import ApiKey, User
from app.models.base import utc_now_iso

KEY_PREFIX = "meloyu_sk_"
MAX_KEYS_PER_USER = 5


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_key(db: Session, user: User, name: str) -> dict:
    name = (name or "").strip()
    if not 1 <= len(name) <= 60:
        raise err_validation(tr("密钥名须为 1~60 字符", "Key name must be 1-60 chars"))
    existing = db.execute(select(ApiKey).where(
        ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None))).scalars().all()
    if len(existing) >= MAX_KEYS_PER_USER:
        raise err_conflict(
            tr(f"每个账号最多 {MAX_KEYS_PER_USER} 个有效密钥，请先吊销旧密钥",
               f"At most {MAX_KEYS_PER_USER} active keys per account; revoke one first"))
    raw = KEY_PREFIX + secrets.token_hex(20)
    now = utc_now_iso()
    row = ApiKey(user_id=user.id, name=name, key_hash=_hash_key(raw),
                 prefix=raw[: len(KEY_PREFIX) + 6],  # meloyu_sk_XXXXXX 前缀供识别
                 created_at=now, updated_at=now)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "prefix": row.prefix,
            "created_at": row.created_at, "last_used_at": None,
            # 完整 key 仅此一次返回（不落明文，丢失只能重新签发）
            "key": raw, "notice": "key 仅创建时完整返回一次，请妥善保存"}


def key_to_dict(k: ApiKey) -> dict:
    return {"id": k.id, "name": k.name, "prefix": k.prefix,
            "created_at": k.created_at, "last_used_at": k.last_used_at}


def list_keys(db: Session, user: User) -> dict:
    rows = db.execute(select(ApiKey).where(
        ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None))
        .order_by(ApiKey.created_at.desc())).scalars().all()
    return {"items": [key_to_dict(k) for k in rows], "total": len(rows)}


def revoke_key(db: Session, user: User, key_id: str) -> dict:
    k = db.get(ApiKey, key_id)
    if k is None or k.user_id != user.id or k.revoked_at is not None:
        raise err_not_found(tr("密钥不存在", "API key not found"))
    k.revoked_at = utc_now_iso()
    k.updated_at = utc_now_iso()
    db.commit()
    return {"ok": True}


def authenticate(db: Session, raw: str | None) -> tuple[User, ApiKey]:
    """公开 API 鉴权：key → (用户, 密钥行)；无效/吊销统一 40101。"""
    from app.core.errors import err_unauthenticated
    raw = (raw or "").strip()
    if not raw.startswith(KEY_PREFIX):
        raise err_unauthenticated()
    row = db.execute(select(ApiKey).where(
        ApiKey.key_hash == _hash_key(raw))).scalars().first()
    if row is None or row.revoked_at is not None:
        raise err_unauthenticated()
    user = db.get(User, row.user_id)
    if user is None:
        raise err_unauthenticated()
    row.last_used_at = utc_now_iso()
    db.commit()
    return user, row
