# Meloyu Docker 部署

将 Meloyu（FastAPI 后端 + React SPA 前端 + PostgreSQL）以生产模式部署到任意
Docker 环境：本机、自有服务器或云主机。

## 拓扑

```
浏览器 ──▶ meloyu-frontend (nginx:alpine)
              │ SPA 静态托管 + /api 反代
              ▼ (独立 bridge 网络)
           meloyu-backend (python:3.12-slim, ENV=production)
              │                    │
              │ 数据卷（音频/日志）  │ DATABASE_URL
              ▼                    ▼
        命名卷或 bind mount    meloyu-postgres (postgres:16-alpine)
                              └ 数据在命名卷 meloyu-pgdata
```

- 后端端口**不对宿主机发布**，仅 nginx 反代可达。
- 前端监听 `8080`（compose 内映射到宿主机 8180，可自行调整）。
- 运行模式 `ENV=production`：弱密钥/`CORS *` 拒绝启动、禁 demo 播种、关闭 `/api/docs`。
- 健康检查 `/api/v1/system/health`：backend 容器内建 HEALTHCHECK，frontend 以
  backend healthy 为启动前置。
- 日志：json-file 10m×3 轮转；应用日志落数据卷 `logs/`。

## 快速开始

```bash
cd deploy
cp env.enterprise.example .env.prod    # 编辑：密钥/数据库口令/CORS 等必填项
docker compose --env-file .env.prod up -d --build
```

启动后访问 `http://<主机>:8180`。首次启动自动执行幂等迁移与建表。

## 环境变量

| 文件 | 用途 |
|---|---|
| `env.enterprise.example` | 企业/服务器栈模板（PostgreSQL 必配） |
| `../backend/.env.example` | 全量变量说明（通道 Key、SMTP、CORS 等） |

关键项：

- `JWT_SECRET` / `POSTGRES_PASSWORD`：必须换成强随机值（production 启动断言会拒绝弱值）。
- `CORS_ORIGINS`：前端实际来源，禁止 `*`。
- `MELOYU_LICENSE_KEY`：企业形态（`APP_MODE=enterprise`）的启动 License 断言。
- 云端生成通道的 Key（Suno 兼容网关 / Replicate 等）均为可选 BYOK，未配置不影响
  本地通道运行。

## 运维要点

- **备份**：PG 数据卷用 `pg_dump` 定期转储；音频/日志卷按目录同步。
- **升级**：拉新镜像/代码后 `docker compose up -d --build`；迁移幂等可重复执行。
- **限流**：应用按请求来源 IP 限流（登录防爆破/注册防批量）；部署在自有反代之后时，
  确保反代以 `$remote_addr` 覆写 `X-Real-IP` / `X-Forwarded-For`，并置
  `TRUST_PROXY=true`。
- 数据库可换云托管（任何 PostgreSQL 兼容服务）：改 `DATABASE_URL` 即可。
