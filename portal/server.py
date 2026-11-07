"""Meloyu License Portal（官网四合一轻服务）。

职责：
1. 营销站——买断制定价 + 购买入口（正式营销站由官网批次细化，此处可运行基座）
2. 购买（buy）——Stripe Payment Link 跳转；履约（thanks）凭 checkout session
   现场签发 License Key（REST 直查 Stripe，无 webhook 依赖；同 session 幂等）
3. License Portal（api/admin/*）——人工签发/吊销/激活设备治理（在线层可选，
   桌面端离线验签不依赖本服务；签名私钥一律离线 license_tools 生成，不经 HTTP）
4. 更新源（updates/）——静态目录托管桌面安装包与 latest.yml

签名实现复用 backend（sys.path 注入），单一事实源：app/services/license.py。
运行：python -m uvicorn server:app --port 8900（在 backend venv 下）。
部署约束：SQLite + 进程内限流 → 必须单进程单 worker（见 README 部署节）。
"""
from __future__ import annotations

import hmac
import html
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
import sys
import threading
import time
import uuid
from email.message import EmailMessage
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

PORTAL_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PORTAL_DIR.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))  # 复用 backend 的 license 签名实现与依赖环境

from app.services.license import sign_license, verify_license_key  # noqa: E402

import db as portal_db  # noqa: E402

DATA_DIR = Path(os.environ.get("PORTAL_DATA_DIR", PORTAL_DIR / "data"))
ADMIN_TOKEN = os.environ.get("PORTAL_ADMIN_TOKEN", "")
# ---- 激活邮件（2026-10-04 用户口径：下单后自动发送账户+激活码邮件） ----
SMTP_HOST = os.environ.get("PORTAL_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("PORTAL_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("PORTAL_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("PORTAL_SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("PORTAL_SMTP_FROM", "Meloyu <no-reply@meloyu.com>")

# 激活码字母表：去易混字符（I/L/O/0/1）
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# /thanks 的 checkout session 强格式：拼入 Stripe API 路径前校验，
# 防路径注入/任意 session 探测
_SESSION_ID_RE = re.compile(r"^cs_(test|live)_[A-Za-z0-9]+$")

# /thanks 页（展示激活码与账户）禁止任何缓存留底
_NO_STORE = {"Cache-Control": "no-store"}


def mask_code(code: str) -> str:
    """激活码日志脱敏：前5后3（如 MELOYU-XXXX…XXX）。

    完整码形如 MELOYU-XXXXXXXX-XXXXXXXX（25 字符）；短于安全长度的输入整体
    打码。日志/工单里不再出现可兑换的完整激活码。
    """
    if not code or len(code) < 12:
        return "MELOYU-***"
    return f"{code[:5]}…{code[-3:]}"


def new_activation_code() -> str:
    def grp() -> str:
        return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
    return f"MELOYU-{grp()}-{grp()}"


def send_activation_email(account: str, code: str, tier: str = "lifetime") -> bool:
    """发送激活邮件（账户+激活码+激活步骤）。SMTP 未配置时返回 False（管理员人工交付兜底）。"""
    if not SMTP_HOST:
        # 兜底邮件行为保持（此处日志即人工交付载体，账户必须可读）；
        # 激活码仍脱敏——完整码只进邮件/交付渠道，不进日志
        print(f"[portal] SMTP not configured; activation email skipped "
              f"(deliver manually): account={account} code={mask_code(code)}")
        return False
    tier_line = ("Lifetime license · all future updates included"
                 if tier == "lifetime" else f"{tier} license")
    msg = EmailMessage()
    msg["Subject"] = "Your Meloyu activation code"
    msg["From"] = SMTP_FROM
    msg["To"] = account
    msg.set_content(f"""Your Meloyu activation details

Your account : {account}
Activation code : {code}
License : {tier_line}

Activate in 3 steps:
1. Open the Meloyu desktop app (download: https://meloyu.com/updates/)
2. Go to "Settings → License"
3. Enter your account and the activation code above

The app works fully offline after activation. If you need help,
reply to this email.

— Meloyu""")
    msg.add_alternative(f"""<html><body style="font-family:ui-monospace,Consolas,monospace;
background:#0d0f10;color:#e8ece9;margin:0;padding:40px 16px">
<div style="max-width:560px;margin:0 auto;background:#16191b;border:1px solid #2a2f33;padding:32px">
<h2 style="color:#8be9c0;margin:0 0 8px">Your Meloyu activation details</h2>
<p style="color:#9aa3a7;font-size:14px">{tier_line}</p>
<table style="margin:16px 0;font-size:14px;color:#e8ece9">
<tr><td style="color:#9aa3a7;padding:6px 12px 6px 0">Your account</td>
<td style="font-weight:700">{html.escape(account)}</td></tr>
<tr><td style="color:#9aa3a7;padding:6px 12px 6px 0">Activation code</td>
<td style="font-weight:700;color:#8be9c0;font-size:16px;letter-spacing:.06em">{code}</td></tr>
</table>
<ol style="color:#9aa3a7;font-size:14px;padding-left:20px">
<li>Open the Meloyu desktop app (download: <a href="https://meloyu.com/updates/" style="color:#8be9c0">meloyu.com/updates</a>)</li>
<li>Go to <b style="color:#e8ece9">Settings → License</b></li>
<li>Enter your account and the activation code above</li>
</ol>
<p style="color:#5c666b;font-size:13px">Works fully offline after activation. Questions? Just reply.</p>
</div></body></html>""", subtype="html")
    try:
        # STARTTLS 必须带证书/主机名校验上下文——否则 SMTP 凭据
        # 可被中间人截获（激活码同通道，等于接管交付链）
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001 —— 邮件失败不阻断售卖（管理员人工兜底）
        print(f"[portal] activation email failed for {account}: {exc!r}")
        return False


PRIVATE_KEY = os.environ.get("PORTAL_PRIVATE_KEY", "")
PUBLIC_KEY = os.environ.get("PORTAL_PUBLIC_KEY", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
PAYMENT_LINK_URL = os.environ.get("PAYMENT_LINK_URL", "")
# 无在线支付模式（默认）：售卖走人工渠道（邮箱联系 → 人工签发 Key）
SALES_EMAIL = os.environ.get("PORTAL_SALES_EMAIL", "")
# 开源免费口径（2026-11-06）：软件本体免费提供，展示面不再出现付费价格；
# 价格常量仅保留在 backend/app/config.py 计费功能内（既有授权/企业服务）。
# 免费获取入口：源码仓库
REPO_URL = "https://github.com/shinychris/meloyu"


# ---------------- 限流 ----------------

class SlidingWindowLimiter:
    """进程内 IP 滑动窗口限流（独立轻量实现，思路同 backend/app/core/ratelimit.py）。

    - admin 防Bearer token 爆破；activate 防激活码枚举与
      签名密钥刷取。
    - 被拒请求同样计入（持续攻击不缩窗）；键按访问惰性过期，键数超上限整体
      清空兜底（内存护栏；最坏=限流窗口重置，无安全影响）。
    - 单进程内存态：portal 必须单进程单 worker 运行（README 部署节）；反代
      之后所有请求同源 TCP 地址，反代层 limit_req 为必配纵深（README 同款）。
    """

    _MAX_KEYS = 10000

    def __init__(self, limit: int, window_sec: float) -> None:
        self.limit = limit
        self.window_sec = window_sec
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """记录一次命中并返回是否放行。"""
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > self._MAX_KEYS:
                self._hits.clear()
            hits = [t for t in self._hits.get(key, ()) if now - t < self.window_sec]
            allowed = len(hits) < self.limit
            hits.append(now)  # 被拒也计数
            self._hits[key] = hits
            return allowed

    def reset(self) -> None:
        """清空计数（测试隔离用）。"""
        with self._lock:
            self._hits.clear()


ADMIN_LIMITER = SlidingWindowLimiter(limit=30, window_sec=60)     # /api/admin/*：30/min/IP
ACTIVATE_LIMITER = SlidingWindowLimiter(limit=10, window_sec=60)  # 激活兑换/上报：10/min/IP


def _client_ip(request: Request) -> str:
    """限流计数键：TCP 对端地址（portal 无 TRUST_PROXY 开关——反代部署按
    README 部署节在反代层做真实 IP 限流，应用层同源计数仅兜底直连形态）。"""
    return request.client.host if request.client else "unknown"


def _rate_limited(request: Request, limiter: SlidingWindowLimiter) -> bool:
    return not limiter.check(_client_ip(request))


app = FastAPI(title="Meloyu License Portal", docs_url=None)


@app.on_event("startup")
async def _startup() -> None:
    """DB init / 数据目录创建等副作用移出 import 期，延后到
    服务启动（uvicorn 会执行 lifespan）；模块可被测试与工具安全导入
    （测试自管 portal_db.init 指向临时库）。"""
    portal_db.init(DATA_DIR / "portal.db")
    (DATA_DIR / "updates").mkdir(parents=True, exist_ok=True)


# ---------------- 鉴权 ----------------

def require_admin(request: Request) -> None:
    client_ip = _client_ip(request)
    # 限流前置：鉴权失败路径同样计数（爆破窗口不被 401 重置）
    if not ADMIN_LIMITER.check(client_ip):
        raise HTTPException(429, "too many requests; retry later")
    if not ADMIN_TOKEN:
        raise HTTPException(503, "admin API disabled: PORTAL_ADMIN_TOKEN not configured")
    auth = request.headers.get("Authorization", "")
    # 常量时间比较（bytes 形态避免非 ASCII 头触发 TypeError）
    if not hmac.compare_digest(auth.encode("utf-8"), f"Bearer {ADMIN_TOKEN}".encode("utf-8")):
        raise HTTPException(401, "invalid admin token")


# ---------------- 签发（人工/履约共用） ----------------

def issue_license(tier: str, account: str, note: str, devices: int, seats: int | None,
                  stripe_session_id: str | None = None, send_email: bool = True) -> dict:
    """签发：完整签名密钥（离线验签）+ 短激活码（在线兑换入口）。

    account = 买家账户（购买邮箱），随激活邮件发送并用于激活时的账户校验。
    """
    if not PRIVATE_KEY:
        raise HTTPException(503, "issuing disabled: PORTAL_PRIVATE_KEY not configured")
    account = (account or "").strip().lower() or None
    code = new_activation_code()
    payload = {
        "lid": uuid.uuid4().hex, "tier": tier,
        "devices": devices if tier == "lifetime" else 1,
        "seats": seats if tier == "enterprise" else None,
        "acct": account, "iat": int(time.time()), "note": note,
    }
    key = sign_license(payload, PRIVATE_KEY)
    with portal_db.conn() as c:
        for _ in range(5):  # 激活码碰撞重试（8+8 去易混字母表实际不可能命中）
            try:
                c.execute(
                    "INSERT INTO licenses (lid, key, code, tier, account, note, devices, "
                    "seats, status, stripe_session_id, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,'active',?,?)",
                    (payload["lid"], key, code, tier, account, note,
                     payload["devices"], payload["seats"],
                     stripe_session_id, portal_db.now_iso()))
                break
            except sqlite3.IntegrityError as exc:
                # 按唯一约束字段区分真实原因，不再宽吞一切 DB 错
                msg = str(exc)
                if "stripe_session_id" in msg and stripe_session_id:
                    # 并发 /thanks 同 session 撞唯一约束：回查已有签发直接复用
                    # （幂等），不重发邮件、不误导报错
                    row = c.execute(
                        "SELECT * FROM licenses WHERE stripe_session_id = ?",
                        (stripe_session_id,)).fetchone()
                    if row is not None:
                        return {"license_id": row["lid"], "tier": row["tier"],
                                "account": row["account"], "note": row["note"],
                                "activation_code": row["code"] or row["key"],
                                "license_key": row["key"], "email_sent": False}
                    raise HTTPException(
                        409, "license already issued for this checkout session") from exc
                code = new_activation_code()  # code 碰撞 → 换码重试
        else:
            raise HTTPException(500, "activation code collision (unreachable)")
    emailed = False
    if send_email and account:
        emailed = send_activation_email(account, code, tier)
    return {"license_id": payload["lid"], "tier": tier, "account": account,
            "note": note, "activation_code": code, "license_key": key,
            "email_sent": emailed}


def license_row(c, lid: str):
    return c.execute("SELECT * FROM licenses WHERE lid = ?", (lid,)).fetchone()


# ---------------- Admin API（人工签发/治理） ----------------

class AdminIssueRequest(BaseModel):
    """人工签发请求体（pydantic 显式校验，非法输入 422 而非 500）。

    devices = 单码可绑定设备数（buy 口径 up to 3，上限放宽到 10）；
    seats = 企业版席位（仅 enterprise 档生效），合理上界 500。
    """
    tier: str = "lifetime"
    account: str = ""
    note: str = ""
    devices: int = Field(default=3, ge=1, le=10)
    seats: int | None = Field(default=None, ge=1, le=500)
    send_email: bool = True


@app.post("/api/admin/licenses")
async def admin_issue(payload: AdminIssueRequest, request: Request):
    require_admin(request)
    if payload.tier not in ("lifetime", "enterprise"):
        raise HTTPException(422, "tier must be lifetime|enterprise")
    return issue_license(payload.tier, payload.account, payload.note,
                         payload.devices, payload.seats,
                         send_email=payload.send_email)


@app.get("/api/admin/licenses")
async def admin_list(request: Request):
    require_admin(request)
    with portal_db.conn() as c:
        rows = c.execute(
            "SELECT lid, tier, account, note, code, status, stripe_session_id, created_at, "
            "(SELECT COUNT(*) FROM activations a WHERE a.lid = l.lid) AS activations "
            "FROM licenses l ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


@app.post("/api/admin/licenses/{lid}/revoke")
async def admin_revoke(lid: str, request: Request):
    require_admin(request)
    with portal_db.conn() as c:
        row = license_row(c, lid)
        if row is None:
            raise HTTPException(404, "license not found")
        c.execute("UPDATE licenses SET status = 'revoked' WHERE lid = ?", (lid,))
        return {"lid": lid, "status": "revoked"}


@app.get("/api/admin/activations")
async def admin_activations(request: Request, lid: str | None = None):
    require_admin(request)
    with portal_db.conn() as c:
        if lid:
            rows = c.execute("SELECT * FROM activations WHERE lid = ? "
                             "ORDER BY activated_at DESC", (lid,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM activations "
                             "ORDER BY activated_at DESC LIMIT 500").fetchall()
        return [dict(r) for r in rows]


@app.delete("/api/admin/activations/{lid}/{device_id}")
async def admin_unbind(lid: str, device_id: str, request: Request):
    """换机解绑（设备治理，2026-10-16）：移除单台设备的激活
    记录、释放设备额度；与整码吊销（revoke）互补，旧设备遗失/退役场景用。"""
    require_admin(request)
    with portal_db.conn() as c:
        cur = c.execute("DELETE FROM activations WHERE lid = ? AND device_id = ?",
                        (lid, device_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "activation not found")
        return {"lid": lid, "device_id": device_id, "unbound": True}


# （api/admin/keygen 端点已删除——经 HTTP 下发签名私钥违背
# 「私钥离线保管」纪律；keypair 一律离线经 backend/scripts/license_tools.py
# keygen 生成，公钥经环境变量注入）


# ---------------- 在线激活上报（治理层，可选） ----------------

@app.post("/api/activate-report")
async def activate_report(request: Request):
    """桌面端可选上报：验签 + 吊销检查 + 设备数治理。离线验签不依赖本端点。"""
    if _rate_limited(request, ACTIVATE_LIMITER):  # 10/min/IP
        raise HTTPException(429, "too many requests; retry later")
    body = await request.json()
    key = (body.get("license_key") or "").strip()
    device_id = (body.get("device_id") or "").strip()
    if not key or not device_id:
        raise HTTPException(422, "license_key and device_id required")
    if PUBLIC_KEY:
        from app.core.errors import BizError
        try:
            # 显式传公钥，消除对全局 settings 的猴补
            verify_license_key(key, public_key_b64=PUBLIC_KEY)
        except BizError:
            return {"ok": False, "reason": "invalid_key"}
    with portal_db.conn() as c:
        row = c.execute("SELECT * FROM licenses WHERE key = ?", (key,)).fetchone()
        if row is None:
            return {"ok": False, "reason": "unknown_license"}
        if row["status"] != "active":
            return {"ok": False, "reason": "revoked"}
        existing = c.execute("SELECT * FROM activations WHERE lid = ? AND device_id = ?",
                             (row["lid"], device_id)).fetchone()
        now = portal_db.now_iso()
        if existing:
            c.execute("UPDATE activations SET last_seen_at = ? WHERE id = ?",
                      (now, existing["id"]))
            return {"ok": True, "remaining_devices": row["devices"]}
        count = c.execute("SELECT COUNT(*) FROM activations WHERE lid = ?",
                          (row["lid"],)).fetchone()[0]
        if count >= row["devices"]:
            return {"ok": False, "reason": "device_limit",
                    "devices": row["devices"]}
        c.execute("INSERT INTO activations (lid, device_id, activated_at, last_seen_at) "
                  "VALUES (?,?,?,?)", (row["lid"], device_id, now, now))
        return {"ok": True, "remaining_devices": row["devices"] - count - 1}


# ---------------- 桌面端在线激活（账户+激活码 → 兑换完整签名密钥） ----------------

@app.post("/api/activate")
async def activate(request: Request):
    """激活码在线兑换（2026-10-04 用户口径）。

    桌面 App 提交 {account, code, device_id} → 校验激活码/账户/吊销/设备数 →
    返回完整签名密钥（App 侧 Ed25519 验签后离线持有，此后不再依赖本服务）。
    """
    if _rate_limited(request, ACTIVATE_LIMITER):  # 10/min/IP
        raise HTTPException(429, "too many requests; retry later")
    body = await request.json()
    account = (body.get("account") or "").strip().lower()
    code = (body.get("code") or "").strip().upper()
    device_id = (body.get("device_id") or "").strip()
    if not (account and code and device_id):
        return {"ok": False, "reason": "invalid_request"}
    with portal_db.conn() as c:
        row = c.execute("SELECT * FROM licenses WHERE code = ?", (code,)).fetchone()
        if row is None:
            return {"ok": False, "reason": "invalid_code"}
        if row["status"] != "active":
            return {"ok": False, "reason": "revoked"}
        if row["account"] and row["account"] != account:
            return {"ok": False, "reason": "account_mismatch"}
        if not row["account"]:
            # 通用码首触绑定（2026-10-16）：人工签发未指定账户的激活码，首次兑换即
            # 锁定兑换账户——防止同一码被任意账户重复领用（此后走上方一致性校验）
            c.execute("UPDATE licenses SET account = ? WHERE lid = ?", (account, row["lid"]))
        existing = c.execute("SELECT id FROM activations WHERE lid = ? AND device_id = ?",
                             (row["lid"], device_id)).fetchone()
        now = portal_db.now_iso()
        if existing:
            c.execute("UPDATE activations SET last_seen_at = ? WHERE id = ?", (now, existing["id"]))
        else:
            count = c.execute("SELECT COUNT(*) FROM activations WHERE lid = ?",
                              (row["lid"],)).fetchone()[0]
            if count >= row["devices"]:
                return {"ok": False, "reason": "device_limit", "devices": row["devices"]}
            c.execute("INSERT INTO activations (lid, device_id, activated_at, last_seen_at) "
                      "VALUES (?,?,?,?)", (row["lid"], device_id, now, now))
        return {"ok": True, "license_key": row["key"], "tier": row["tier"],
                "license_id": row["lid"], "devices": row["devices"]}


# ---------------- 获取：免费下载 + 激活码（Payment Link 链路保留） ----------------

@app.get("/buy")
async def buy():
    """获取入口（开源免费口径，2026-11-06）：

    - 默认（零外部依赖）：免费下载（源码仓库）+ 激活码获取说明——既有授权、
      企业授权与商用证书沿用人工签发链路（邮箱联系 → /api/admin/licenses 签发）；
    - 在线支付（可选，计费功能保留）：配 PAYMENT_LINK_URL → 302 Stripe
      Payment Link，履约走 /thanks（运营按需启用）。
    """
    if PAYMENT_LINK_URL:
        return RedirectResponse(PAYMENT_LINK_URL)
    contact = html.escape(SALES_EMAIL or "support@meloyu.com")  #
    repo = html.escape(REPO_URL)
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8">
<title>Meloyu — Free &amp; Open Source</title>
<style>body{{font-family:ui-monospace,Consolas,monospace;background:#0d0f10;
color:#e8ece9;display:flex;align-items:center;justify-content:center;height:100vh;
margin:0}}.card{{max-width:560px;padding:40px;background:#16191b;border:1px solid #2a2f33}}
h2{{color:#8be9c0;margin:0 0 12px}}.price{{font-size:40px;font-weight:800;margin:16px 0}}
a{{color:#8be9c0}}li{{margin:8px 0;color:#9aa3a7;font-size:14px}}</style></head><body>
<div class="card"><h2>Meloyu Desktop — Free &amp; Open Source</h2>
<div class="price">Free</div>
<ol>
<li>Download the app or the source code from <a href="{repo}">{repo}</a> — free under the MIT license.</li>
<li>Need an activation code (existing lifetime license, enterprise or commercial-use licensing)? Email <a href="mailto:{contact}">{contact}</a>.</li>
<li>You receive an activation email with your account and activation code (usually within 24 hours).</li>
<li>Open Meloyu → Settings → License → enter your account + code. Done.</li>
</ol>
<p style="color:#5c666b;font-size:13px">Free &amp; open source (MIT) · existing lifetime licenses remain valid ·
up to 3 devices · all future updates included.</p>
</div></body></html>""")


@app.get("/thanks")
async def thanks(session_id: str = ""):
    """Payment Link 支付完成回跳：直查 Stripe 校验已付 → 幂等签发 → 页面展示 Key。"""
    if not _SESSION_ID_RE.fullmatch(session_id):
        # session_id 拼入 Stripe API 路径前强格式校验
        # （cs_test_/cs_live_ 前缀 + 字母数字，防路径注入与任意 id 探测）
        raise HTTPException(422, "invalid checkout session id")
    if not (STRIPE_SECRET_KEY and PRIVATE_KEY):
        contact = html.escape(SALES_EMAIL or "support@meloyu.com")
        return HTMLResponse(
            f"<h3>Online payment verification is not enabled on this portal. "
            f"Forward your receipt to <a href='mailto:{contact}'>{contact}</a> and your "
            f"license key will be emailed.</h3>", headers=_NO_STORE)
    # 幂等：同 session 已签发则直接复现
    with portal_db.conn() as c:
        row = c.execute("SELECT * FROM licenses WHERE stripe_session_id = ?",
                        (session_id,)).fetchone()
    if row is None:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.stripe.com/v1/checkout/sessions/{session_id}",
                auth=(STRIPE_SECRET_KEY, ""), timeout=15)
        if r.status_code != 200:
            raise HTTPException(502, "failed to verify payment with Stripe")
        session = r.json()
        if (session.get("payment_status") != "paid"
                or session.get("status") != "complete"):
            return HTMLResponse("<h3>This payment is not completed yet. "
                                "Refresh after your payment succeeds.</h3>",
                                status_code=402, headers=_NO_STORE)
        email = ((session.get("customer_details") or {}).get("email") or "")
        issued = issue_license("lifetime", email, "", 3, None,
                               stripe_session_id=session_id)
        key = issued["activation_code"]
        note = email
    else:
        key = row["code"] or row["key"]
        note = row["account"] or row["note"]
    # 页面展示完整激活码 + 账户——插值全部 html.escape（防御纵深），
    # 且响应 no-store，防浏览器/代理缓存留底
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8">
<title>Meloyu — Your license key</title>
<style>body{{font-family:ui-monospace,Consolas,monospace;background:#0d0f10;
color:#e8ece9;display:flex;align-items:center;justify-content:center;height:100vh;
margin:0}}.card{{max-width:640px;padding:40px;background:#16191b;border:1px solid #2a2f33}}
h2{{color:#8be9c0;margin:0 0 8px}}.note{{color:#9aa3a7;font-size:13px}}
.key{{margin:24px 0;padding:16px;background:#0d0f10;border:1px dashed #8be9c0;
word-break:break-all;font-size:12px;line-height:1.6}}</style></head><body>
<div class="card"><h2>Payment received — your activation code</h2>
<div class="note">Licensed to: {html.escape(note or '—')}</div>
<div class="note">Copy this activation code into Meloyu → Settings → License
(also emailed to you with your account):</div>
<div class="key">{html.escape(key)}</div>
<div class="note">Keep this page or your activation email. One license covers up to 3 of your devices.</div>
</div></body></html>""", headers=_NO_STORE)


# ---------------- 更新源（静态：latest.yml + 安装包上传至此） ----------------
# check_dir=False：目录创建已移入 startup 钩子，import 期不落盘
app.mount("/updates", StaticFiles(directory=str(DATA_DIR / "updates"), check_dir=False),
          name="updates")


# ---------------- 营销站（F7：landing 独立构建 dist-landing；未构建时兜底基座页） ----------------

LANDING_DIR = Path(os.environ.get(
    "PORTAL_LANDING_DIR", PORTAL_DIR.parent / "frontend" / "dist-landing"))
# 兜底基座页：插值仅构建期仓库链接常量（str，无用户可控数据），无转义需求
_FALLBACK_PAGE = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Meloyu — AI Music Desktop Studio</title>
<style>body{{font-family:ui-monospace,Consolas,monospace;background:#0d0f10;
color:#e8ece9;display:flex;align-items:center;justify-content:center;height:100vh;
margin:0;flex-direction:column;gap:16px}}
.price{{font-size:56px;font-weight:800;color:#8be9c0}}
a.btn{{background:#8be9c0;color:#0d0f10;padding:14px 34px;text-decoration:none;
font-weight:700}}</style></head><body>
<div style="letter-spacing:.2em;font-weight:700">MELOYU</div>
<div>AI Music Desktop Studio — free &amp; open source</div>
<div class="price">Free</div>
<a class="btn" href="/buy">Get Meloyu — Free</a>
<div style="color:#5c666b;font-size:13px">MIT licensed · macOS &amp; Windows ·
all future updates included</div>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    """营销站首页：dist-landing 已构建则回落地页 SPA（默认 en，zh 可切），
    否则回兜底基座页（构建指引见 portal/README.md）。"""
    landing_html = LANDING_DIR / "landing.html"
    if landing_html.is_file():
        return FileResponse(landing_html)
    return HTMLResponse(_FALLBACK_PAGE)



@app.get("/healthz")
async def healthz():
    return {"ok": True}

# 营销站静态资源挂载（assets/*）：必须置于全部路由注册之后——
# Starlette 按注册顺序匹配，"/" 挂载会吞掉其后才注册的 API 路由（测试实测）
if LANDING_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(LANDING_DIR)), name="site")
