"""桌面单机形态支撑（B6）：本地档案自动建档 + 免登录短路。

desktop 模式下系统有且仅有一个本地用户（local@meloyu.desktop，随机密码）：
- 首次启动自动建档（plan=studio：试用/激活均视同全功能档，权益差异由
  License 试用闸门而非 plan 字段表达）；
- get_current_user / get_current_user_optional 无凭证时直接返回该用户
  （本地实例无信任边界，账号体系整体短路，JWT 基础设施原样保留）。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password
from app.models import User
from app.models.base import utc_now_iso
from app.services.license import get_state, new_local_password

LOCAL_USER_EMAIL = "local@meloyu.desktop"


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
