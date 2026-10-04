"""License 服务（2026-10-03 定位转型：买断制终身授权 + 14 天试用，D-1/D-2）。

Key 格式（离线可验，Ed25519）：
    v1.<body_b64url>.<sig_b64url>
    body = 紧凑 JSON {"lid": 授权id, "tier": lifetime|enterprise, "devices": N,
                      "seats": N, "iat": epoch, "note": "买家备注"}
    sig  = Ed25519(private, body_b64url 的 ASCII 字节)

- 验签纯本地（公钥环境注入），断网可用；在线激活端点（portal）仅做
  设备数治理与吊销，不阻断离线使用。
- 激活 = 验签通过后写 license_state + 本地用户 plan（desktop：studio 全功能），
  下游全部权益闸门（配额/导出/证书/队列优先级）零改动。
- 试用闸门（B12）：desktop 形态未激活且试用到期 → 生成/派生/导出一律 40203 拦截。
"""
from __future__ import annotations

import base64
import json
import secrets
from datetime import UTC, datetime, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy.orm import Session

from app.config import LICENSE_PRICE_USD, LICENSE_SALE_PRICE_USD, LICENSE_TRIAL_DAYS, settings
from app.core.errors import BizError, err_conflict
from app.core.i18n import tr
from app.models import User
from app.models.base import utc_now_iso
from app.models.license_state import STATE_ID, LicenseState

ERR_LICENSE_INVALID = 40202
ERR_LICENSE_REQUIRED = 40203

_TIERS = ("lifetime", "enterprise")
_ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def err_license_invalid(msg: str) -> BizError:
    return BizError(ERR_LICENSE_INVALID, msg, 422)


def err_license_required(msg: str) -> BizError:
    return BizError(ERR_LICENSE_REQUIRED, msg, 402)


# ---- keypair / 签发（portal 与 scripts.license_tools 复用）----

def generate_keypair() -> tuple[str, str]:
    """生成 Ed25519 keypair，返回 (private_b64, public_b64)（32 字节原始密钥）。"""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    priv_b64 = base64.b64encode(priv.private_bytes_raw()).decode("ascii")
    pub_b64 = base64.b64encode(pub.public_bytes_raw()).decode("ascii")
    return priv_b64, pub_b64


def sign_license(payload: dict, private_key_b64: str) -> str:
    """按 Key 格式签发授权：v1.<body>.<sig>。"""
    priv = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64))
    body = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
                   .encode("utf-8"))
    sig = _b64url(priv.sign(body.encode("ascii")))
    return f"v1.{body}.{sig}"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _public_key() -> Ed25519PublicKey:
    raw = settings.license_public_key.strip()
    if not raw:
        raise err_license_invalid(tr(
            "本实例未配置 License 公钥（LICENSE_PUBLIC_KEY），无法激活",
            "No license public key configured (LICENSE_PUBLIC_KEY); "
            "activation unavailable"))
    try:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(raw))
    except Exception as exc:
        raise err_license_invalid("LICENSE_PUBLIC_KEY 配置无效") from exc


def verify_license_key(key: str) -> dict:
    """验签并返回载荷 dict；格式/签名/tier 无效抛 40202。"""
    key = (key or "").strip()
    parts = key.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        raise err_license_invalid(tr("License Key 格式无效", "Invalid license key format"))
    body, sig = parts[1], parts[2]
    try:
        _public_key().verify(_b64url_decode(sig), body.encode("ascii"))
        payload = json.loads(_b64url_decode(body))
    except InvalidSignature:
        raise err_license_invalid(tr(
            "License Key 验签失败（密钥无效或非本产品授权）",
            "License key signature verification failed "
            "(invalid key or not issued for this product)")) from None
    except err_license_invalid:
        raise
    except Exception as exc:
        raise err_license_invalid(tr("License Key 解析失败", "Failed to parse license key")) from exc
    if payload.get("tier") not in _TIERS:
        raise err_license_invalid(tr("License Key 档位无效", "Invalid license tier"))
    return payload


# ---- 状态（单行表）----

def get_state(db: Session) -> LicenseState:
    """读取（或惰性创建）本机 License 状态；首次访问即落试用起点。"""
    state = db.get(LicenseState, STATE_ID)
    if state is None:
        state = LicenseState(id=STATE_ID, trial_started_at=utc_now_iso())
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def _started_at(state: LicenseState) -> datetime:
    return datetime.strptime(state.trial_started_at, _ISO_FMT).replace(tzinfo=UTC)


def _trial_expired(state: LicenseState) -> bool:
    return datetime.now(UTC) >= _started_at(state) + timedelta(days=LICENSE_TRIAL_DAYS)


def status_dict(db: Session) -> dict:
    state = get_state(db)
    activated = state.license_key is not None
    expires = days_left = None
    if not activated:
        elapsed_days = int((datetime.now(UTC) - _started_at(state)).total_seconds() // 86400)
        expires = (_started_at(state) + timedelta(days=LICENSE_TRIAL_DAYS)).strftime(_ISO_FMT)
        days_left = max(0, LICENSE_TRIAL_DAYS - elapsed_days)
    return {
        "mode": settings.app_mode,
        "billing_mode": settings.billing_mode,
        "trial": {
            "started_at": state.trial_started_at,
            "days": LICENSE_TRIAL_DAYS,
            "days_left": days_left,
            "expires_at": expires,
            "expired": _trial_expired(state) and not activated,
        },
        "activated": activated,
        "license": ({"license_id": (state.license_payload or {}).get("lid"),
                     "tier": (state.license_payload or {}).get("tier"),
                     "devices": (state.license_payload or {}).get("devices", 1),
                     "account": ((state.license_payload or {}).get("acct")
                                 or (state.license_payload or {}).get("note")),
                     "note": (state.license_payload or {}).get("note"),
                     "activated_at": state.activated_at}
                    if activated else None),
        "device_id": state.device_id,
        "price_usd": LICENSE_PRICE_USD,
        "sale_price_usd": LICENSE_SALE_PRICE_USD,
    }


def activate(db: Session, key: str, user: User | None = None) -> dict:
    """激活：验签 → 写状态 → 本地用户升到全功能档（lifetime=studio / enterprise=team）。"""
    payload = verify_license_key(key)
    state = get_state(db)
    if state.license_key == key.strip():
        return status_dict(db)  # 幂等：重复激活同一 Key
    state.license_key = key.strip()
    state.license_payload = payload
    state.activated_at = utc_now_iso()
    if user is not None:
        user.plan = "studio" if payload["tier"] == "lifetime" else "team"
        user.updated_at = utc_now_iso()
    db.commit()
    return status_dict(db)


def _unreachable_error() -> BizError:
    return err_conflict(tr(
        "无法连接激活服务（{}）——请检查网络后重试，或使用邮件中的完整授权密钥离线激活",
        "Cannot reach the activation service ({}); check your network and retry, "
        "or paste the full license key from your email for offline activation"
    ).format(settings.portal_base_url))


def _portal_activate(account: str, code: str, device_id: str) -> dict:
    """调用 portal 激活码兑换端点；网络/超时抛 40901 引导（离线密钥激活兜底）。"""
    import httpx
    url = settings.portal_base_url.rstrip("/") + "/api/activate"
    try:
        resp = httpx.post(url, json={"account": account, "code": code,
                                     "device_id": device_id},
                          timeout=settings.portal_activate_timeout_sec)
        return resp.json()
    except Exception as exc:
        raise _unreachable_error() from exc


_REASONS = {
    "invalid_code": ("激活码无效（请核对邮件中的账户与激活码）",
                     "Invalid activation code (check the account and code in your email)"),
    "account_mismatch": ("激活码与账户不匹配——请使用购买邮箱作为账户",
                         "Activation code does not match this account; "
                         "use the email you purchased with"),
    "revoked": ("该激活码已被吊销——请联系支持",
                "This activation code has been revoked; contact support"),
    "device_limit": ("激活设备数已达上限——请在其他设备上解绑后重试",
                     "Device limit reached; deactivate on another device first"),
}


def activate_online(db: Session, user: User | None, account: str, code: str,
                    *, _fetch=None) -> dict:
    """在线激活（2026-10-04 用户口径）：账户+激活码 → portal 兑换完整签名密钥
    → 本地 Ed25519 验签 → 落激活态。激活后离线持有密钥，不再依赖网络。

    _fetch：单测注入（签名 (account, code, device_id) → portal 响应 dict）。
    """
    state = get_state(db)
    fetch = _fetch or _portal_activate
    try:
        resp = fetch(account.strip().lower(), code.strip().upper(), state.device_id)
    except BizError:
        raise
    except Exception as exc:  # 注入/网络层异常统一转 40901 离线激活引导
        raise _unreachable_error() from exc
    if not isinstance(resp, dict) or not resp.get("ok"):
        reason = (resp or {}).get("reason", "invalid_code") if isinstance(resp, dict) else "invalid_code"
        zh, en = _REASONS.get(reason, _REASONS["invalid_code"])
        raise err_license_invalid(tr(zh, en))
    key = resp.get("license_key") or ""
    payload = verify_license_key(key)  # 签名密钥仍须过本地验签（防服务端异常数据）
    if payload.get("acct") and payload["acct"] != account.strip().lower():
        raise err_license_invalid(tr("授权密钥与账户不匹配",
                                     "License key does not match this account"))
    return activate(db, key, user=user)


def deactivate(db: Session) -> dict:
    """解除激活（保留试用记录；到期后由试用闸门接管）。"""
    state = get_state(db)
    state.license_key = None
    state.license_payload = None
    state.activated_at = None
    db.commit()
    return status_dict(db)


def ensure_generation_allowed(db: Session) -> None:
    """B12 试用闸门：desktop/enterprise 形态，未激活且试用到期 → 40203 拦截。

    仅拦截新的生成/派生/导出提交；已有作品的浏览/播放不受影响。
    """
    if settings.app_mode not in ("desktop", "enterprise"):
        return
    state = db.get(LicenseState, STATE_ID)
    if state is not None and state.license_key is not None:
        return
    if state is None or not _trial_expired(state):
        return
    raise err_license_required(tr(
        f"试用期已结束——{LICENSE_TRIAL_DAYS} 天全功能试用到期后需终身授权才能继续创作。"
        "请前往「定价与激活」输入 License Key 完成激活。",
        f"Your {LICENSE_TRIAL_DAYS}-day trial has ended — a lifetime license is "
        "required to keep creating. Enter your license key under Pricing & Activation."))


def assert_enterprise_license() -> None:
    """enterprise 启动断言：License Key 必须有效（fail-fast，防未授权部署）。"""
    if settings.app_mode != "enterprise":
        return
    key = settings.meloyu_license_key.strip()
    if not key:
        raise RuntimeError("enterprise mode requires MELOYU_LICENSE_KEY "
                           "(issued by the Meloyu license portal)")
    payload = verify_license_key(key)
    if payload.get("tier") != "enterprise":
        raise RuntimeError("MELOYU_LICENSE_KEY is not an enterprise-tier license")


def new_local_password() -> str:
    """桌面本地档案随机密码（用户无感知，静默登录）。"""
    return secrets.token_urlsafe(24)
