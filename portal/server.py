"""Meloyu License Portal（P3，2026-10-03 定位转型 · 官网四合一轻服务）。

职责（方案 §6.4）：
1. 营销站（/）——买断制定价 + 购买入口（正式营销站由官网批次细化，此处可运行基座）
2. 购买（/buy）——Stripe Payment Link 跳转；履约（/thanks）凭 checkout session
   现场签发 License Key（REST 直查 Stripe，无 webhook 依赖；同 session 幂等）
3. License Portal（/api/admin/*）——人工签发/吊销/激活设备治理（在线层可选，
   桌面端离线验签不依赖本服务）
4. 更新源（/updates/）——静态目录托管桌面安装包与 latest.yml

签名实现复用 backend（sys.path 注入），单一事实源：app/services/license.py。
运行：python -m uvicorn server:app --port 8900（在 backend venv 下）。
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

PORTAL_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PORTAL_DIR.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))  # 复用 backend 的 license 签名实现与依赖环境

from app.services.license import generate_keypair, sign_license, verify_license_key  # noqa: E402

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


def new_activation_code() -> str:
    import secrets
    def grp() -> str:
        return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
    return f"MELOYU-{grp()}-{grp()}"


def send_activation_email(account: str, code: str, tier: str = "lifetime") -> bool:
    """发送激活邮件（账户+激活码+激活步骤）。SMTP 未配置时返回 False（管理员人工交付兜底）。"""
    if not SMTP_HOST:
        print(f"[portal] SMTP not configured; activation email skipped "
              f"(deliver manually): account={account} code={code}")
        return False
    import smtplib
    from email.message import EmailMessage
    tier_line = ("Lifetime license · all future updates included"
                 if tier == "lifetime" else f"{tier} license")
    msg = EmailMessage()
    msg["Subject"] = "Your Meloyu activation code"
    msg["From"] = SMTP_FROM
    msg["To"] = account
    msg.set_content(f"""Thank you for buying Meloyu!

Your account : {account}
Activation code : {code}
License : {tier_line}

Activate in 3 steps:
1. Open the Meloyu desktop app (download: https://meloyu.com/updates/)
2. Go to "Pricing & Activation"
3. Enter your account and the activation code above

The app works fully offline after activation. If you need help,
reply to this email.

— Meloyu""")
    msg.add_alternative(f"""<html><body style="font-family:ui-monospace,Consolas,monospace;
background:#0d0f10;color:#e8ece9;margin:0;padding:40px 16px">
<div style="max-width:560px;margin:0 auto;background:#16191b;border:1px solid #2a2f33;padding:32px">
<h2 style="color:#8be9c0;margin:0 0 8px">Thank you for buying Meloyu</h2>
<p style="color:#9aa3a7;font-size:14px">{tier_line}</p>
<table style="margin:16px 0;font-size:14px;color:#e8ece9">
<tr><td style="color:#9aa3a7;padding:6px 12px 6px 0">Your account</td>
<td style="font-weight:700">{account}</td></tr>
<tr><td style="color:#9aa3a7;padding:6px 12px 6px 0">Activation code</td>
<td style="font-weight:700;color:#8be9c0;font-size:16px;letter-spacing:.06em">{code}</td></tr>
</table>
<ol style="color:#9aa3a7;font-size:14px;padding-left:20px">
<li>Open the Meloyu desktop app (download: <a href="https://meloyu.com/updates/" style="color:#8be9c0">meloyu.com/updates</a>)</li>
<li>Go to <b style="color:#e8ece9">Pricing &amp; Activation</b></li>
<li>Enter your account and the activation code above</li>
</ol>
<p style="color:#5c666b;font-size:13px">Works fully offline after activation. Questions? Just reply.</p>
</div></body></html>""", subtype="html")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
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
PRICE_USD = 39900
SALE_PRICE_USD = 15900

app = FastAPI(title="Meloyu License Portal", docs_url=None)
portal_db.init(DATA_DIR / "portal.db")
(DATA_DIR / "updates").mkdir(parents=True, exist_ok=True)


# ---------------- 鉴权 ----------------

def require_admin(request: Request) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(503, "admin API disabled: PORTAL_ADMIN_TOKEN not configured")
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {ADMIN_TOKEN}":
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
        "acct": account, "iat": int(__import__("time").time()), "note": note,
    }
    key = sign_license(payload, PRIVATE_KEY)
    with portal_db.conn() as c:
        for _ in range(5):  # 激活码碰撞重试（8+8 base32 实际不可能命中）
            try:
                c.execute(
                    "INSERT INTO licenses (lid, key, code, tier, account, note, devices, "
                    "seats, status, stripe_session_id, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,'active',?,?)",
                    (payload["lid"], key, code, tier, account, note,
                     payload["devices"], payload["seats"],
                     stripe_session_id, portal_db.now_iso()))
                break
            except Exception:
                code = new_activation_code()
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

@app.post("/api/admin/licenses")
async def admin_issue(request: Request):
    require_admin(request)
    body = await request.json()
    tier = body.get("tier", "lifetime")
    if tier not in ("lifetime", "enterprise"):
        raise HTTPException(422, "tier must be lifetime|enterprise")
    return issue_license(tier, body.get("account", ""), body.get("note", ""),
                         int(body.get("devices", 3)), body.get("seats"),
                         send_email=body.get("send_email", True))


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


@app.post("/api/admin/keygen")
async def admin_keygen(request: Request):
    """轮换 keypair（慎重：旧 Key 全部失效，需同步更新 App 内公钥）。"""
    require_admin(request)
    priv, pub = generate_keypair()
    return {"private_key": priv, "public_key": pub,
            "warning": "store the private key offline; embed the public key via "
                       "LICENSE_PUBLIC_KEY at build time"}


# ---------------- 在线激活上报（治理层，可选） ----------------

@app.post("/api/activate-report")
async def activate_report(request: Request):
    """桌面端可选上报：验签 + 吊销检查 + 设备数治理。离线验签不依赖本端点。"""
    body = await request.json()
    key = (body.get("license_key") or "").strip()
    device_id = (body.get("device_id") or "").strip()
    if not key or not device_id:
        raise HTTPException(422, "license_key and device_id required")
    if PUBLIC_KEY:
        import app.config as cfg
        from app.core.errors import BizError
        old = cfg.settings.license_public_key
        cfg.settings.license_public_key = PUBLIC_KEY
        try:
            verify_license_key(key)
        except BizError:
            return {"ok": False, "reason": "invalid_key"}
        finally:
            cfg.settings.license_public_key = old
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


# ---------------- 购买：Payment Link 跳转 + 现场履约 ----------------

@app.get("/buy")
async def buy():
    """购买入口（双模式）：

    - 在线支付（可选）：配 PAYMENT_LINK_URL → 302 Stripe Payment Link，履约走 /thanks；
    - 人工签发（默认，零外部依赖）：未配支付链接 → 联系购买页（邮箱/流程说明），
      管理员经 /api/admin/licenses 人工签发后交付 Key。
    """
    if PAYMENT_LINK_URL:
        return RedirectResponse(PAYMENT_LINK_URL)
    contact = SALES_EMAIL or "support@meloyu.com"
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8">
<title>Meloyu — Get your license</title>
<style>body{{font-family:ui-monospace,Consolas,monospace;background:#0d0f10;
color:#e8ece9;display:flex;align-items:center;justify-content:center;height:100vh;
margin:0}}.card{{max-width:560px;padding:40px;background:#16191b;border:1px solid #2a2f33}}
h2{{color:#8be9c0;margin:0 0 12px}}.price{{font-size:40px;font-weight:800;margin:16px 0}}
a{{color:#8be9c0}}li{{margin:8px 0;color:#9aa3a7;font-size:14px}}</style></head><body>
<div class="card"><h2>Meloyu Desktop — Lifetime License</h2>
<div class="price">$159 <span style="font-size:16px;color:#5c666b;text-decoration:line-through">$399</span></div>
<ol>
<li>Email <a href="mailto:{contact}">{contact}</a> to purchase (launch-offer $159, one-time, lifetime).</li>
<li>You receive an activation email with your account and activation code (usually within 24 hours).</li>
<li>Open Meloyu → Pricing &amp; Activation → enter your account + code. Done.</li>
</ol>
<p style="color:#5c666b;font-size:13px">One-time purchase · up to 3 devices · all future updates included ·
14-day full-feature trial in the app before you buy.</p>
</div></body></html>""")


@app.get("/thanks")
async def thanks(session_id: str = ""):
    """Payment Link 支付完成回跳：直查 Stripe 校验已付 → 幂等签发 → 页面展示 Key。"""
    if not session_id:
        return HTMLResponse("<h3>Missing checkout session.</h3>", status_code=422)
    if not (STRIPE_SECRET_KEY and PRIVATE_KEY):
        contact = SALES_EMAIL or "support@meloyu.com"
        return HTMLResponse(
            f"<h3>Online payment verification is not enabled on this portal. "
            f"Forward your receipt to <a href='mailto:{contact}'>{contact}</a> and your "
            f"license key will be emailed.</h3>")
    # 幂等：同 session 已签发则直接复现
    with portal_db.conn() as c:
        row = c.execute("SELECT * FROM licenses WHERE stripe_session_id = ?",
                        (session_id,)).fetchone()
    if row is None:
        import httpx
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
                                "Refresh after your payment succeeds.</h3>", status_code=402)
        email = ((session.get("customer_details") or {}).get("email") or "")
        issued = issue_license("lifetime", email, "", 3, None,
                               stripe_session_id=session_id)
        key = issued["activation_code"]
        note = email
    else:
        key = row["code"] or row["key"]
        note = row["account"] or row["note"]
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8">
<title>Meloyu — Your license key</title>
<style>body{{font-family:ui-monospace,Consolas,monospace;background:#0d0f10;
color:#e8ece9;display:flex;align-items:center;justify-content:center;height:100vh;
margin:0}}.card{{max-width:640px;padding:40px;background:#16191b;border:1px solid #2a2f33}}
h2{{color:#8be9c0;margin:0 0 8px}}.note{{color:#9aa3a7;font-size:13px}}
.key{{margin:24px 0;padding:16px;background:#0d0f10;border:1px dashed #8be9c0;
word-break:break-all;font-size:12px;line-height:1.6}}</style></head><body>
<div class="card"><h2>Payment received — your activation code</h2>
<div class="note">Licensed to: {note or '—'}</div>
<div class="note">Copy this activation code into Meloyu → Pricing &amp; Activation
(also emailed to you with your account):</div>
<div class="key">{key}</div>
<div class="note">Keep this page or your activation email. One license covers up to 3 of your devices.</div>
</div></body></html>""")


# ---------------- 更新源（静态：latest.yml + 安装包上传至此） ----------------

app.mount("/updates", StaticFiles(directory=str(DATA_DIR / "updates")), name="updates")


# ---------------- 营销站（F7：landing 独立构建 dist-landing；未构建时兜底基座页） ----------------

LANDING_DIR = Path(os.environ.get(
    "PORTAL_LANDING_DIR", PORTAL_DIR.parent / "frontend" / "dist-landing"))
_FALLBACK_PAGE = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Meloyu — AI Music Desktop Studio</title>
<style>body{{font-family:ui-monospace,Consolas,monospace;background:#0d0f10;
color:#e8ece9;display:flex;align-items:center;justify-content:center;height:100vh;
margin:0;flex-direction:column;gap:16px}}
.price{{font-size:56px;font-weight:800;color:#8be9c0}}
a.btn{{background:#8be9c0;color:#0d0f10;padding:14px 34px;text-decoration:none;
font-weight:700}}</style></head><body>
<div style="letter-spacing:.2em;font-weight:700">MELOYU</div>
<div>AI Music Desktop Studio — one purchase, yours for life</div>
<div class="price">${SALE_PRICE_USD // 100}
<span style="font-size:20px;color:#5c666b;text-decoration:line-through">
${PRICE_USD // 100}</span></div>
<a class="btn" href="/buy">Buy lifetime license</a>
<div style="color:#5c666b;font-size:13px">Launch offer · macOS &amp; Windows ·
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
