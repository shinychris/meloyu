"""邮件发送（stdlib smtplib，零新依赖）与注册验证码。

- SMTP 未配置（settings.smtp_host 为空）时：邮件相关功能整体不可用，
  forgot-password / send-code 返回 40901 明确提示需管理员配置 SMTP。
- 发送健壮性（2026-09-26）：SMTP 异常不再裸抛 500——转 40901
  "邮件服务暂不可用"业务错误，并做一次退避重试（网络抖动自愈）。
- 验证码：落库 email_codes（仅存 sha256，TTL 10 分钟，重发节流
  60 秒），重启/多副本可用；注册成功或验证通过即删行。
"""
from __future__ import annotations

import hashlib
import hmac
import smtplib
import time
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import delete, select

from app.config import settings
from app.core.errors import err_conflict
from app.core.i18n import tr
from app.core.logging import logger

CODE_TTL_SEC = 10 * 60
CODE_RESEND_SEC = 60


def smtp_configured() -> bool:
    return bool(settings.smtp_host)


def _require_smtp() -> None:
    if not smtp_configured():
        raise err_conflict(tr(
            "邮件服务未配置，请联系管理员（SMTP）",
            "Email service is not configured; please contact the administrator (SMTP)"))


def _deliver(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


def _send(to: str, subject: str, body: str) -> None:
    """发送 + 一次退避重试；两次都失败转 40901 业务错误。"""
    _require_smtp()
    last_exc: Exception | None = None
    for attempt in (1, 2):
        try:
            _deliver(to, subject, body)
            logger.info(f"mail sent to {to}: {subject}")
            return
        except (smtplib.SMTPException, OSError) as e:  # noqa: PERF203
            last_exc = e
            if attempt == 1:
                time.sleep(2)  # 抖动退避，只重试一次
    logger.error(f"mail send failed to {to}: {last_exc!r}")
    raise err_conflict(tr(
        "邮件发送失败（服务暂不可用），请稍后重试",
        "Failed to send email (service temporarily unavailable); try again later"))


def send_raw(to: str, subject: str, body: str) -> None:
    """通用文本邮件（系统通知类：dunning 催付等；调用方自行兜错）。"""
    _send(to, subject, body)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def send_verification_code(db, email: str) -> None:
    """注册验证码：生成 6 位数字码、落库哈希、发信；60s 内重发被拒。"""
    import secrets

    from app.models import EmailCode

    _require_smtp()
    now = datetime.now(UTC)
    recent = db.execute(
        select(EmailCode.id).where(
            EmailCode.email == email,
            EmailCode.created_at > (now - timedelta(seconds=CODE_RESEND_SEC))
            .strftime("%Y-%m-%dT%H:%M:%SZ")).limit(1)
    ).first()
    if recent:
        raise err_conflict(tr("验证码发送过于频繁，请稍后再试",
                              "Verification code sent too frequently; try again later"))
    code = f"{secrets.randbelow(1000000):06d}"
    digest = hashlib.sha256(code.encode()).hexdigest()
    expires = (now + timedelta(seconds=CODE_TTL_SEC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(delete(EmailCode).where(EmailCode.email == email))  # 每邮箱至多一条活跃码
    db.add(EmailCode(email=email, code_sha256=digest, expires_at=expires,
                     created_at=_now_iso(), updated_at=_now_iso()))
    db.commit()
    # 邮件按发起请求的 Accept-Language 单语发送（en 用户不再收到中英混排）
    _send(email, tr("Meloyu 验证码", "Meloyu verification code"),
          tr(f"您的 Meloyu 验证码为 {code}，10 分钟内有效。",
             f"Your Meloyu verification code is {code}. It expires in 10 minutes."))


def verify_code(db, email: str, code: str) -> bool:
    from app.models import EmailCode

    row = db.execute(select(EmailCode).where(
        EmailCode.email == email).limit(1)).scalars().first()
    if not row:
        return False
    if row.expires_at <= _now_iso():
        db.delete(row)
        db.commit()
        return False
    return hmac.compare_digest(row.code_sha256,
                               hashlib.sha256(code.encode()).hexdigest())


def consume_code(db, email: str) -> None:
    from app.models import EmailCode

    db.execute(delete(EmailCode).where(EmailCode.email == email))
    db.commit()


def send_password_reset_email(email: str, reset_url: str) -> None:
    _send(email, tr("Meloyu 找回密码", "Meloyu password reset"),
          tr(f"重置您的 Meloyu 密码（30 分钟内有效）：\n{reset_url}",
             f"Reset your Meloyu password (valid for 30 minutes):\n{reset_url}"))
