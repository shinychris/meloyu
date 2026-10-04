# Meloyu License Portal（官网四合一轻服务，P3）

> 2026-10-03 定位转型后的 meloyu.com 承载形态（方案 §6.4）：营销站基座 +
> 购买（Stripe Payment Link）+ License 签发与设备治理 + 桌面更新源。
> 复用 backend 的 Ed25519 签名实现（`backend/app/services/license.py`，单一事实源），
> 运行在 backend venv 上，零新增 Python 依赖。

## 售卖双模式（2026-10-04 口径）

- **人工签发（默认，零外部依赖）**：不配 `PAYMENT_LINK_URL`，`/buy` 展示联系购买页
  （`PORTAL_SALES_EMAIL` 定制邮箱）；管理员经 `POST /api/admin/licenses` 签发 Key
  邮件交付。适合起步期/小单量，无任何第三方依赖。
- **在线支付（可选）**：配 `PAYMENT_LINK_URL`（Stripe Payment Link）+
  `STRIPE_SECRET_KEY`，`/buy` 302 跳转、`/thanks` 自动履约（见下节）。桌面客户端
  本身不含任何支付代码。

## 运行

```bash
cd portal
# backend venv 下（依赖 fastapi/httpx 均已在 requirements.txt）
set PORTAL_ADMIN_TOKEN=<强随机>
set PORTAL_PRIVATE_KEY=<license_tools keygen 的 private_key>
set PORTAL_PUBLIC_KEY=<同 keypair 的 public_key>
set STRIPE_SECRET_KEY=sk_live_...          # /thanks 履约校验用（可选）
set PAYMENT_LINK_URL=https://buy.stripe.com/...   # Dashboard 建 Payment Link 后填
../backend/.venv/Scripts/python.exe -m uvicorn server:app --port 8900
```

生产部署：Dokploy 上新建服务（复用现有栈的域名/TLS），或与官网静态站同机。

## 端点

| 端点 | 说明 |
|---|---|
| `GET /` | 官网营销站：landing 独立构建（`cd frontend && npm run build:landing` → `dist-landing/`，默认英文、zh 可切、买断定价与购买入口）；未构建时兜底基座页 |
| `GET /buy` | 302 → Stripe Payment Link |
| `GET /thanks?session_id=` | 支付完成回跳：直查 Stripe 校验已付 → **幂等签发** → 页面展示 Key |
| `POST /api/activate-report` | 桌面端可选在线上报：验签/吊销/设备数治理（离线验签不依赖） |
| `POST /api/admin/licenses` | 人工签发 `{tier: lifetime\|enterprise, note, devices, seats}` |
| `GET /api/admin/licenses` | 签发列表（含激活数） |
| `POST /api/admin/licenses/{lid}/revoke` | 吊销 |
| `GET /api/admin/activations` | 设备激活记录 |
| `POST /api/admin/keygen` | keypair 轮换（慎重：旧 Key 全失效，需同步 App 公钥） |
| `/updates/*` | 更新源静态目录（`data/updates/` 上传 latest.yml + 安装包） |

Admin 端点鉴权：`Authorization: Bearer <PORTAL_ADMIN_TOKEN>`。

## 购买闭环（Stripe Payment Link，无 webhook）

1. Stripe Dashboard 创建 **Payment Link**（$159，成功后跳转
   `https://<portal>/thanks?session_id={CHECKOUT_SESSION_ID}`）→ 填 `PAYMENT_LINK_URL`。
2. 用户付款 → 回跳 `/thanks` → 服务端凭 secret key 直查
   `GET /v1/checkout/sessions/{id}` 确认 `payment_status=paid` → 签发终身 Key
   （`stripe_session_id` 唯一约束保证幂等）→ 页面展示。
3. 用户复制 Key → 桌面端「定价与激活」粘贴激活（或购买邮件里放
   `meloyu://activate?key=...` 深度链接一键激活）。

## 测试

```bash
cd portal && ../backend/.venv/Scripts/python.exe -m unittest test_portal
```
