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
