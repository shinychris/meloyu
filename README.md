# Meloyu · AI 音乐创作系统（桌面买断制）

> 2026-10-03 定位转型定案：SaaS 订阅 → **桌面软件买断**（macOS/Windows，
> $399 终身授权 / 限时首发 $159）+ 企业私有化部署服务。
> 完整方案：[docs/06-商业化/2026-10-03-定位调整方案-SaaS转桌面买断制.md](docs/06-商业化/2026-10-03-定位调整方案-SaaS转桌面买断制.md)

## 仓库结构

| 目录 | 说明 |
|---|---|
| `backend/` | FastAPI 单体（一单体三形态：`APP_MODE=desktop|cloud|enterprise`）：七通道歌曲生成、歌词 LLM 双通道、任务/作品/导出/证书、License Ed25519 验签、桌面 sidecar 入口（`scripts/desktop_runner.py`） |
| `frontend/` | React 19 + Vite SPA：工作台/歌词/编曲/作品库/定价与激活/模型中心；同一份代码两处运行——桌面壳（dist/）与官网营销站（`build:landing` → dist-landing/） |
| `desktop/` | Electron 壳（P2）：sidecar 生命周期/深度链接/CSP/托盘/自动更新/打包（electron-builder NSIS + dmg）；三方许可声明 `THIRD-PARTY-NOTICES.md` |
| `portal/` | 官网四合一轻服务（P3）：营销站托管 + 购买（默认人工签发，Stripe 可选）+ License Portal（激活码签发/在线兑换/设备治理/换机解绑）+ 更新源 |
| `deploy/` | Docker 企业栈（PG + backend + frontend）、备份/监控脚本、`env.enterprise.example` |
| `docs/` | 架构/契约/商业化方案与 runbook（`docs/06-商业化/`） |

## 快速开始（桌面版开发链路）

```bash
# 后端（desktop 形态，SQLite，数据落 ~/Meloyu）
cd backend && python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
APP_MODE=desktop .venv/Scripts/python -m uvicorn app.main:app --port 8000

# 前端产物 + 壳
cd frontend && npm install && npm run build
cd ../desktop && npm install && npm start
```

打包发布（Windows NSIS 实跑验证通过；macOS dmg 需 mac 主机）：见
[desktop/README.md](desktop/README.md)。

## 测试

```bash
cd backend && .venv/Scripts/python -m unittest discover -s tests   # 226 用例
cd frontend && npm test                                            # 114 用例
cd portal && ../backend/.venv/Scripts/python.exe -m unittest test_portal  # 9 用例
cd desktop && npm test                                             # node:test 6 用例
```

版本：**v0.16.2**（版本事实源五处一致：config.APP_VERSION / 前后端+壳 package.json / pyproject / CHANGELOG）。
