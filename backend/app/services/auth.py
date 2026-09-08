"""认证服务：注册（赠 200 积分/邮箱验证码/管理员授予）/ 登录 / me /
刷新令牌轮换 / 找回重置密码 / 改密 / 注销（匿名化）/ 数据导出（P1-3，v0.7.0）。"""
from __future__ import annotations

import io
import json
import shutil
import zipfile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import SIGNUP_BONUS_CREDITS, settings
from app.core.errors import BizError, err_bad_credentials, err_conflict, err_validation
from app.core.i18n import tr
from app.core.security import (
    create_access_token,
    create_reset_token,
    decode_reset_token,
    hash_password,
    issue_refresh_token,
    revoke_refresh_token,
    verify_password,
    verify_refresh_token,
)
from app.models import CreditTransaction, Subscription, User, Work
from app.models.base import utc_now_iso
from app.services import credits as credits_svc
from app.services import mail as mail_svc
from app.services.serializers import user_to_dict


def _admin_emails() -> set[str]:
    return {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}


def register(db: Session, email: str, password: str, nickname: str,
             code: str | None = None) -> dict:
    email = email.strip().lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise err_conflict(tr("该邮箱已注册", "This email is already registered"))
    if settings.email_verification_enabled:
        if not code or not mail_svc.verify_code(email, code):
            raise err_validation(tr("邮箱验证码错误或已过期",
                                    "Email verification code is invalid or expired"))
    now = utc_now_iso()
    user = User(email=email, password_hash=hash_password(password), nickname=nickname,
                plan="free", is_admin=email in _admin_emails(),
                email_verified=settings.email_verification_enabled,
                created_at=now, updated_at=now)
    db.add(user)
    db.flush()
    db.add(Subscription(user_id=user.id, plan="free", status="active", started_at=now,
                        source="signup", granted_credits=0, created_at=now, updated_at=now))
    credits_svc.grant(db, user, SIGNUP_BONUS_CREDITS, "signup_bonus")
    out, refresh, refresh_ttl = _with_tokens(user)
    db.commit()  # refresh_token_hash 必须随响应落库（否则会话关闭即丢失）
    db.refresh(user)
    mail_svc.consume_code(email)
    return out, refresh, refresh_ttl


def login(db: Session, email: str, password: str) -> tuple[dict, str, int]:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not verify_password(password, user.password_hash):
        raise err_bad_credentials()
    credits_svc.lazy_monthly_grant(db, user)
    out, refresh, refresh_ttl = _with_tokens(user)
    db.commit()  # refresh_token_hash 必须随响应落库（否则会话关闭即丢失）
    db.refresh(user)
    return out, refresh, refresh_ttl


def me(db: Session, user: User) -> dict:
    credits_svc.lazy_monthly_grant(db, user)
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


def refresh(db: Session, refresh_token: str) -> tuple[dict, str, int]:
    """刷新令牌轮换：校验旧 refresh → 签发新 access + 新 refresh（单设备语义）。"""
    import hashlib
    digest = hashlib.sha256(refresh_token.encode("ascii")).hexdigest()
    # 无状态定位用户：按存储的 hash 反查（users 表全量小，可接受）
    user = db.query(User).filter(User.refresh_token_hash.like(f"%|{digest}")).first()
    if user is None or not verify_refresh_token(user, refresh_token):
        raise err_bad_credentials(tr("刷新令牌无效或已过期",
                                     "Refresh token is invalid or expired"))
    credits_svc.lazy_monthly_grant(db, user)
    out, new_refresh, refresh_ttl = _with_tokens(user)
    db.commit()  # 轮换后的新 refresh 必须落库（旧 hash 已被覆写=自动失效）
    db.refresh(user)
    return out, new_refresh, refresh_ttl


def logout(db: Session, user: User) -> dict:
    revoke_refresh_token(user)
    user.updated_at = utc_now_iso()
    db.commit()
    return {"ok": True}


def forgot_password(db: Session, email: str) -> dict:
    """发起找回密码：无论账号是否存在都返回 ok（不泄漏注册状态），存在则发信。

    v0.10.2：SMTP 未配置时账号存在会抛 40901、不存在返回 ok——可被用于枚举
    注册邮箱。改为存在账号但发信失败时统一吞掉异常记日志，对调用方恒 ok。"""
    from loguru import logger
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user is not None:
        token = create_reset_token(user)
        url = f"{settings.app_base_url}/#/reset-password?token={token}"
        try:
            mail_svc.send_password_reset_email(user.email, url)
        except BizError as e:
            # SMTP 未配置/发信失败：不向调用方区分（防枚举），运维面记日志告警
            logger.warning(f"password-reset mail failed for {user.email}: {e.message}")
    return {"ok": True}


def reset_password(db: Session, token: str, new_password: str) -> dict:
    user_id = decode_reset_token(token)
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise err_validation(tr("重置链接无效或已过期",
                                "Reset link is invalid or expired"))
    user.password_hash = hash_password(new_password)
    revoke_refresh_token(user)  # 吊销全部既有会话
    user.updated_at = utc_now_iso()
    db.commit()
    return {"ok": True}


def change_password(db: Session, user: User, old_password: str, new_password: str) -> dict:
    if not verify_password(old_password, user.password_hash):
        raise err_bad_credentials(tr("当前密码错误", "Current password is incorrect"))
    user.password_hash = hash_password(new_password)
    revoke_refresh_token(user)
    user.updated_at = utc_now_iso()
    db.commit()
    return {"ok": True}


def delete_account(db: Session, user: User, password: str) -> dict:
    """账号注销（个保法删除权）：密码确认 → 删除全部作品与音频文件 → 用户行匿名化。

    - 账本（credit_transactions）保留：财务合规留存，仅关联匿名化后的用户行；
    - 用户行不物理删除（works/tasks 外键 RESTRICT，且账本需引用）：
      email/nickname 化名、密码置随机、清 refresh/计划字段。
    """
    if not verify_password(password, user.password_hash):
        raise err_bad_credentials(tr("密码错误", "Incorrect password"))
    import secrets as _secrets
    works = db.execute(select(Work).where(Work.user_id == user.id)).scalars().all()
    removed_works = 0
    for w in works:
        shutil.rmtree(settings.audio_path / w.id, ignore_errors=True)
        db.delete(w)  # 级联 versions/candidates/files/events/certificates
        removed_works += 1
    user.email = f"deleted-{user.id}@deleted.meloyu.invalid"
    user.nickname = "deleted"
    user.password_hash = hash_password(_secrets.token_urlsafe(24))
    user.plan = "free"
    user.credit_balance = 0
    user.credit_monthly_grant = 0
    user.credit_carried_over = 0
    user.credit_next_grant_at = None
    user.refresh_token_hash = None
    user.is_admin = False
    user.email_verified = False
    user.updated_at = utc_now_iso()
    db.commit()
    return {"ok": True, "works_removed": removed_works}


def export_data(db: Session, user: User) -> tuple[str, bytes]:
    """个人数据导出（个保法复制权）：资料/作品元数据/账本 JSON 打包 zip。"""
    from app.models import Certificate, Task, Version

    works = db.execute(select(Work).where(Work.user_id == user.id)).scalars().all()
    payload = {
        "exported_at": utc_now_iso(),
        "profile": user_to_dict(user),
        "works": [],
        "credit_transactions": [],
    }
    for w in works:
        versions = db.execute(
            select(Version).where(Version.work_id == w.id)).scalars().all()
        certs = db.execute(
            select(Certificate).where(Certificate.work_id == w.id)).scalars().all()
        payload["works"].append({
            "work": w.to_dict(),
            "versions": [v.to_dict() for v in versions],
            "certificates": [c.to_dict() for c in certs],
        })
    txs = db.execute(select(CreditTransaction)
                     .where(CreditTransaction.user_id == user.id)
                     .order_by(CreditTransaction.created_at.asc())).scalars().all()
    payload["credit_transactions"] = [t.to_dict() for t in txs]
    tasks = db.execute(select(Task).where(Task.user_id == user.id)).scalars().all()
    payload["tasks"] = [t.to_dict() for t in tasks]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("meloyu-data-export.json",
                    json.dumps(payload, ensure_ascii=False, indent=2))
    filename = f"meloyu-export-{user.id[:8]}.zip"
    return filename, buf.getvalue()


def _with_tokens(user: User) -> tuple[dict, str, int]:
    """组装登录/注册/刷新响应；返回 (body_data, refresh_token, refresh_ttl)。

    安审计 M-1/M-2（2026-09-09）：refresh token 不再进响应体（localStorage
    可被任意同源 JS 读取，XSS 后 30 天凭据失窃）——由路由层改经
    HttpOnly+SameSite=Strict Cookie 下发（api/v1/auth.py）。body 仅保留
    access_token（24h，XSS 窃取窗口有界；轮换式 refresh 在 HttpOnly 域）。
    """
    data = user_to_dict(user)
    data["access_token"] = create_access_token(user)
    data["token_type"] = "Bearer"
    refresh, ttl = issue_refresh_token(user)
    data["expires_in"] = 24 * 3600
    data["refresh_expires_in"] = ttl
    return data, refresh, ttl
