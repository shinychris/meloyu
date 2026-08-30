"""认证服务：注册（赠 200 积分）/ 登录 / me。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import SIGNUP_BONUS_CREDITS
from app.core.errors import err_bad_credentials, err_conflict
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Subscription, User
from app.models.base import utc_now_iso
from app.services import credits as credits_svc
from app.services.serializers import user_to_dict


def register(db: Session, email: str, password: str, nickname: str) -> dict:
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise err_conflict("该邮箱已注册")
    now = utc_now_iso()
    user = User(email=email, password_hash=hash_password(password), nickname=nickname,
                plan="free", created_at=now, updated_at=now)
    db.add(user)
    db.flush()
    db.add(Subscription(user_id=user.id, plan="free", status="active", started_at=now,
                        source="signup", granted_credits=0, created_at=now, updated_at=now))
    credits_svc.grant(db, user, SIGNUP_BONUS_CREDITS, "signup_bonus")
    db.commit()
    db.refresh(user)
    return _with_token(user)


def login(db: Session, email: str, password: str) -> dict:
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise err_bad_credentials()
    credits_svc.lazy_monthly_grant(db, user)
    db.commit()
    db.refresh(user)
    return _with_token(user)


def me(db: Session, user: User) -> dict:
    credits_svc.lazy_monthly_grant(db, user)
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


def _with_token(user: User) -> dict:
    data = user_to_dict(user)
    data["access_token"] = create_access_token(user)
    data["token_type"] = "Bearer"
    data["expires_in"] = 7 * 24 * 3600
    return data
