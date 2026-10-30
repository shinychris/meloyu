# Meloyu License Portal（官网四合一轻服务，P3）

> 2026-10-03 定位转型后的 meloyu.com 承载形态（方案 §6.4）：营销站 +
> 购买（默认人工签发，Stripe Payment Link 可选）+ License 签发与设备治理
> （含换机解绑）+ 桌面更新源。复用 backend 的 Ed25519 签名实现
> （`backend/app/services/license.py`，单一事实源），运行在 backend venv 上，
> 零新增 Python 依赖。

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
set PORTAL_SMTP_HOST=...  # 激活邮件发件箱（未配置=日志打印人工交付）
# 在线支付（可选，默认人工签发模式无需配置）：
set STRIPE_SECRET_KEY=sk_live_...
set PAYMENT_LINK_URL=https://buy.stripe.com/...
../backend/.venv/Scripts/python.exe -m uvicorn server:app --port 8900
```

生产部署：Dokploy 上新建服务（复用现有栈的域名/TLS），或与官网静态站同机。

## 生产部署约束（必读）

- **必须单进程单 worker 运行**：存储为 SQLite（单写入方），进程内限流/状态
  均为内存态。uvicorn 不得加 `--workers`、不得多副本；需要扩容先迁移 PG +
  Redis 后端。
- **反代层限流为必配项**：应用内限流按 TCP 对端地址计数，反代之后所有请求
  同源（仅兜底直连形态）。nginx 反代必须加（示例，对敏感端点收口）：

  ```nginx
  limit_req_zone $binary_remote_addr zone=portal_sensitive:10m rate=10r/m;
  location /api/activate     { limit_req zone=portal_sensitive burst=5 nodelay; proxy_pass ...; }
  location /api/activate-report { limit_req zone=portal_sensitive burst=5 nodelay; proxy_pass ...; }
  location /api/admin/       { limit_req zone=portal_sensitive burst=5 nodelay; proxy_pass ...; }
  ```

  应用层另有进程内滑动窗口（admin 30/min/IP、activate 10/min/IP，鉴权失败
  同样计数）作为第一道防线。
- **私钥不入服务**：`PORTAL_PRIVATE_KEY` 仅注入签发服务（在线履约需要），
  keypair 生成一律离线 `python -m scripts.license_tools keygen`（backend venv），
  **不存在也不得新增经 HTTP 下发私钥的端点**（原 /api/admin/keygen 已删除）。

## 端点

| 端点 | 说明 |
|---|---|
| `GET /` | 官网营销站：landing 独立构建（`cd frontend && npm run build:landing` → `dist-landing/`，默认英文、zh 可切、买断定价与购买入口）；未构建时兜底基座页 |
| `GET /buy` | 购买入口：默认人工签发联系页（价格/邮箱流程/激活邮件说明）；配 `PAYMENT_LINK_URL` 后 302 在线支付 |
| `GET /thanks?session_id=` | 在线支付回跳（可选层）：直查 Stripe 校验已付 → **幂等签发** → 页面展示激活码 |
| `POST /api/activate` | **桌面端在线激活**：`{account, code, device_id}` → 校验激活码/账户/吊销/设备数 → 返回完整签名密钥（App 兑换后离线持有）；未指定账户的码首次兑换即锁定账户 |
| `POST /api/activate-report` | 桌面端可选在线上报：验签/吊销/设备数治理（离线验签不依赖） |
| `POST /api/admin/licenses` | 人工签发 `{tier: lifetime\|enterprise, account, note, devices(1-10), seats(1-500, enterprise)}`（带 account 自动发激活邮件） |
| `GET /api/admin/licenses` | 签发列表（含激活数） |
| `POST /api/admin/licenses/{lid}/revoke` | 整码吊销 |
| `GET /api/admin/activations` | 设备激活记录（可按 lid 过滤） |
| `DELETE /api/admin/activations/{lid}/{device_id}` | **换机解绑**：移除单台设备激活记录、释放设备额度（v0.16.2） |
| `/updates/*` | 更新源静态目录（`data/updates/` 上传 latest.yml + 安装包） |

Admin 端点鉴权：`Authorization: Bearer <PORTAL_ADMIN_TOKEN>`（常量时间比较；
admin/activate 端点均带进程内 IP 限流，见「生产部署约束」）。

## 激活邮件（2026-10-04 口径）

下单/签发即发送（`PORTAL_SMTP_*` 环境变量配置发件箱，STARTTLS 强制证书
校验）：邮件含**用户账户（购买邮箱）+ 激活码**（`MELOYU-XXXXXXXX-XXXXXXXX`）
+ 三步激活指引 + 深度链接。SMTP 未配置时跳过发送并在日志打印账户 +
**脱敏激活码**（前5后3）供管理员人工交付（完整码只在邮件/交付渠道，不进日志）。
桌面端输入账户+激活码在线兑换（仅需联网一次），完整授权密钥粘贴激活保留为
离线备用。

## 购买闭环

**默认（人工签发，零外部依赖）**：用户 `/buy` 联系购买 → 管理员
`POST /api/admin/licenses`（填买家邮箱）→ 激活邮件自动发送（SMTP 未配置时日志
打印人工交付）→ 用户在桌面端输入账户+激活码激活。

**可选（Stripe Payment Link，无 webhook）**：

1. Stripe Dashboard 创建 **Payment Link**（$129，成功后跳转
   `https://<portal>/thanks?session_id={CHECKOUT_SESSION_ID}`）→ 填 `PAYMENT_LINK_URL`。
2. 用户付款 → 回跳 `/thanks` → 服务端凭 secret key 直查
   `GET /v1/checkout/sessions/{id}` 确认 `payment_status=paid` → 签发激活码
   （`stripe_session_id` 唯一约束保证幂等）→ 页面展示 + 邮件交付。
3. 用户在桌面端输入账户+激活码激活（或激活邮件深链
   `meloyu://activate?account=..&code=..` 一键激活）。

## 测试（18 用例）

```bash
cd portal && ../backend/.venv/Scripts/python.exe -m unittest test_portal
```

临时库/目录走 `tempfile` + atexit 自动清理，不落仓库根。
