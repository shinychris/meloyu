"""桌面单机形态支撑（B6）：本地档案自动建档 + 免登录短路 + 实例密钥自生成。

desktop 模式下系统有且仅有一个本地用户（local@meloyu.desktop，随机密码）：
- 首次启动自动建档（plan=studio：试用/激活均视同全功能档，权益差异由
  License 试用闸门而非 plan 字段表达）；
- get_current_user / get_current_user_optional 无凭证时直接返回该用户
  （本地实例无信任边界，账号体系整体短路，JWT 基础设施原样保留）。
"""
from __future__ import annotations

import json
import secrets as pysecrets
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import logger
from app.core.security import hash_password
from app.models import User
from app.models.base import utc_now_iso
from app.services.license import get_state, new_local_password

LOCAL_USER_EMAIL = "local@meloyu.desktop"

# config.py 的 dev 默认值（仅用于识别“未显式配置”状态，不在此复制定义）
_DEV_JWT_SECRET = "meloyu-dev-secret-do-not-use-in-production"


def ensure_desktop_secrets(root: Path | None = None) -> Path:
    """桌面实例密钥首启生成与持久化（幂等；B1/B7 补全，2026-10-16）。

    - jwt_secret：摆脱全局公开默认值——否则任意本机进程可伪造 stream-token
      / access token（B6 短路后账号作用弱化，但签名密钥仍不应公开可知）；
    - key_encryption_secret：Fernet 密钥，模型中心 BYOK Key 落库加密的前置
      （未配置时明文直通，与“本机加密存储”设计相悖）；
    - env 显式配置优先（调试/企业定制场景可覆盖）；密钥文件=数据目录
      .secrets.json，与作品数据同生命周期：文件在即复用，丢失即换钥——
      代价是已发 token 失效、已存密文 Key 需重新录入（本地密钥的标准语义）。

    仅由 main.py 桌面启动路径调用（测试可显式传 root 隔离），须先于
    reencrypt_plaintext_secrets 等密钥消费点执行。
    """
    from cryptography.fernet import Fernet

    target = (root or settings.data_path) / ".secrets.json"
    data: dict[str, str] = {}
    if target.is_file():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = {k: v for k, v in loaded.items() if isinstance(v, str)}
        except (OSError, ValueError):
            logger.warning(f"desktop secrets file unreadable, regenerating: {target}")
            data = {}
    file_dirty = False
    if not settings.jwt_secret or settings.jwt_secret == _DEV_JWT_SECRET:
        if not data.get("jwt_secret"):
            data["jwt_secret"] = pysecrets.token_urlsafe(48)
            file_dirty = True
        settings.jwt_secret = data["jwt_secret"]
    if not settings.key_encryption_secret:
        if not data.get("key_encryption_secret"):
            data["key_encryption_secret"] = Fernet.generate_key().decode("ascii")
            file_dirty = True
        settings.key_encryption_secret = data["key_encryption_secret"]
    if file_dirty:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(f"desktop mode: instance secrets generated at {target}")
    return target



def ensure_local_user(db: Session) -> User:
    """读取或创建桌面本地档案（幂等；首次调用同时落试用起点）。"""
    user = db.execute(select(User).where(User.email == LOCAL_USER_EMAIL)).scalars().first()
    if user is not None:
        return user
    get_state(db)  # 首启即记录试用起点（D-2：14 天全功能试用）
    now = utc_now_iso()
    user = User(email=LOCAL_USER_EMAIL, password_hash=hash_password(new_local_password()),
                nickname="Meloyu", plan="studio", credit_balance=0,
                is_admin=True, created_at=now, updated_at=now)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_local_user(db: Session) -> User | None:
    """读取本地档案（不创建）；供鉴权短路使用。"""
    return db.execute(select(User).where(User.email == LOCAL_USER_EMAIL)).scalars().first()


def desktop_mode() -> bool:
    return settings.app_mode == "desktop"
