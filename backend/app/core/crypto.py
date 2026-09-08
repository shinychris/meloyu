"""API Key 落库加密（P1-2，盘点报告 R-12 修复：Fernet 对称加密）。

- KEY_ENCRYPTION_SECRET 未配置（dev 默认）：明文直通 + 单次警告——本地单机自用
  可接受；生产部署应配置（openssl rand -base64 32）。
- 兼容历史明文：decrypt 失败（非 Fernet token）时原样返回，写入侧统一加密，
  存量数据随下次保存自然升级为密文。
"""
from __future__ import annotations

from app.config import settings
from app.core.logging import logger

_warned = False


def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(settings.key_encryption_secret.encode("ascii"))


def encryption_enabled() -> bool:
    return bool(settings.key_encryption_secret)


def encrypt_secret(plain: str) -> str:
    if not plain or not encryption_enabled():
        if not encryption_enabled() and plain and not _warned:
            logger.warning("KEY_ENCRYPTION_SECRET not configured; "
                           "API keys stored in plaintext (dev mode)")
        return plain
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(stored: str) -> str:
    if not stored or not encryption_enabled():
        return stored
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(stored.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return stored  # 历史明文兼容：原样返回


def reencrypt_plaintext_secrets() -> int:
    """启动自愈：把历史明文密钥字段升级为密文（安审计 M-2，2026-09-09）。

    判定与 decrypt 的兼容口径一致：当前密钥解不开（InvalidToken）即视为
    明文，重新加密落库——否则存量明文行除非用户重新保存，将永远明文。
    未配置加密密钥时直接跳过（返回 0）。返回升级的字段数。
    """
    if not encryption_enabled():
        return 0
    from cryptography.fernet import InvalidToken
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import LLMSetting

    fields = ("external_api_key", "music_api_key", "replicate_api_token")
    upgraded = 0
    with SessionLocal() as db:
        rows = db.execute(select(LLMSetting)).scalars().all()
        for row in rows:
            dirty = False
            for f in fields:
                stored = getattr(row, f) or ""
                if not stored:
                    continue
                try:
                    _fernet().decrypt(stored.encode("ascii"))
                except (InvalidToken, ValueError):
                    setattr(row, f, encrypt_secret(stored))
                    upgraded += 1
                    dirty = True
            if dirty:
                db.add(row)
        if upgraded:
            db.commit()
    return upgraded
