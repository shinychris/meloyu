# Meloyu Desktop（Electron 壳）

> 2026-10-03 定位转型（P2）：SaaS → 桌面软件买断制。壳 = Electron 主进程 +
> FastAPI sidecar（`APP_MODE=desktop`，SQLite + 免登录 + 试用期/License 激活）+
> 同源托管的前端 SPA（`frontend/dist`）。方案：`docs/06-商业化/2026-10-03-定位调整方案-SaaS转桌面买断制.md`。

## 架构

```
Electron 主进程（src/main.js）
 ├─ 单实例锁 + meloyu://activate 深度链接（购买邮件一键激活）
 ├─ pickFreePort → spawn sidecar（127.0.0.1 随机端口）
 ├─ 健康检查 /api/v1/system/health → loadURL http://127.0.0.1:<port>
 ├─ 麦克风权限（哼唱/人声克隆）、外链走系统浏览器、electron-updater
 └─ 退出优雅关停 sidecar（SIGTERM → 3s 强杀）

sidecar（backend 打包，scripts/desktop_runner.py）
 ├─ APP_MODE=desktop：SQLite、本地档案免登录、14 天试用 + License 激活
 ├─ DESKTOP_STATIC_DIR=resources/web → 同源托管前端（Cookie 刷新机制原样）
 └─ DATA_DIR=<userData>/data（作品/库/权重随用户目录，升级不丢数据）
```

## 开发运行（Windows 示例）

```bash
# 1) 后端（backend venv 已就位）
cd backend && .venv\Scripts\python -m uvicorn app.main:app --port 8000
# 2) 前端产物（壳直接吃 dist，无需 vite dev server）
cd frontend && npm run build
# 3) 壳（dev 模式直连 127.0.0.1:8000）
cd desktop && npm install && npm start
#    或者让壳自己拉 sidecar：set MELOYU_DEV_SIDECAR=1 && npm start
```

## 打包发布（按序三步）

```bash
# ① sidecar（backend/dist-backend/meloyu-backend/）
desktop\sidecar\build-sidecar.cmd        # Windows
desktop/sidecar/build-sidecar.sh         # macOS

# ② 前端
cd frontend && npm run build

# ③ 壳（desktop/release/ 产出安装包）
cd desktop && npm run dist:win           # NSIS x64
cd desktop && npm run dist:mac           # dmg arm64 + x64
```

## 签名与公证（GA 前置，P0 证书采购项）

- **Windows**：`electron-builder.yml` `win.certificateSubjectName` 配 EV 证书主题；
  PyInstaller 产物误报是已知问题，正式版必须签名 + 提交微软误报申诉。
  首选 Azure Trusted Signing（无硬件令牌）。
- **macOS**：`mac.identity = "Developer ID Application: <主体>"` + `notarize: true`；
  **sidecar 二进制必须与主程序同签**（afterSign 钩子里对
  `resources/meloyu-backend/**` 逐个 `codesign` 后统一 `notarytool submit`）。
- 构建机注入 `LICENSE_PUBLIC_KEY`（sidecar 验签公钥，keypair 由
  `backend/scripts/license_tools.py keygen` 生成；私钥离线保管，用于签发）。

## 自动更新

- 更新源：官网静态目录（P3，`https://meloyu.com/updates/`，Dokploy/nginx 或 R2 CDN）。
- 打包机注入 `MELOYU_UPDATE_URL` 启用 electron-updater（generic provider），
  `latest.yml` 由 electron-builder 随包产出，直接上传更新目录即可。
- 更新权利随 License 验签放行（方案 §4.3：终身授权含全部版本更新）。

## 已知边界

- 本地大模型（ACE-Step / MusicGen 权重）不随包分发，首启后经「组件中心」
  按需下载（ModelOp 管线已有；组件中心 UI 为后续批次）。
- 云通道（Suno 网关 / Replicate）为 BYOK：用户在模型中心自配 Key（桌面本地
  档案 is_admin，配置面即面向用户）。
- macOS 本地推理以 MusicGen(CPU)+内置引擎保底；ACE-Step mac 构建未验证。
