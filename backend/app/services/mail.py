"""邮件发送（stdlib smtplib，零新依赖）与注册验证码缓存（P0-6）。

- SMTP 未配置（settings.smtp_host 为空）时：邮件相关功能整体不可用，
  forgot-password / send-code 返回 40901 明确提示需管理员配置 SMTP。
- 验证码：单进程内存缓存（email → sha256(code)+过期时间），有效期 10 分钟，
  发送间隔 60 秒防刷；注册成功后清除。进程重启失效（重新发码即可，无持久化必要）。
"""
from __future__ import annotations

import hashlib
import hmac
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from app.config import settings
from app.core.errors import err_conflict
from app.core.i18n import tr
from app.core.logging import logger

CODE_TTL_SEC = 10 * 60
CODE_RESEND_SEC = 60

# 内存缓存：email → (code_sha256, expires_iso, last_sent_iso)
_codes: dict[str, tuple[str, str, str]] = {}


def smtp_configured() -> bool:
    return bool(settings.smtp_host)


def _require_smtp() -> None:
    if not smtp_configured():
        raise err_conflict(tr(
            "邮件服务未配置，请联系管理员（SMTP）",
            "Email service is not configured; please contact the administrator (SMTP)"))


def _send(to: str, subject: str, body: str) -> None:
    _require_smtp()
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
    logger.info(f"mail sent to {to}: {subject}")


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def send_verification_code(email: str) -> None:
    """注册验证码：生成 6 位数字码、缓存哈希、发信；60s 内重发被拒。"""
    import secrets

    _require_smtp()
    entry = _codes.get(email)
    now = datetime.now(UTC)
    if entry and entry[2] > (now - timedelta(seconds=CODE_RESEND_SEC)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"):
        raise err_conflict(tr("验证码发送过于频繁，请稍后再试",
                              "Verification code sent too frequently; try again later"))
    code = f"{secrets.randbelow(1000000):06d}"
    digest = hashlib.sha256(code.encode()).hexdigest()
    expires = (now + timedelta(seconds=CODE_TTL_SEC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _codes[email] = (digest, expires, _now_iso())
    _send(email, "Meloyu verification code / 验证码",
          f"Your Meloyu verification code is {code}. It expires in 10 minutes.\n"
          f"您的 Meloyu 验证码为 {code}，10 分钟内有效。")


def verify_code(email: str, code: str) -> bool:
    entry = _codes.get(email)
    if not entry:
        return False
    digest, expires, _ = entry
    if expires <= _now_iso():
        _codes.pop(email, None)
        return False
    return hmac.compare_digest(digest, hashlib.sha256(code.encode()).hexdigest())


def consume_code(email: str) -> None:
    _codes.pop(email, None)


def send_password_reset_email(email: str, reset_url: str) -> None:
    _send(email, "Meloyu password reset / 找回密码",
          f"Reset your Meloyu password (valid 30 minutes):\n{reset_url}\n\n"
          f"重置您的 Meloyu 密码（30 分钟内有效）：\n{reset_url}")
