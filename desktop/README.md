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

## 签名与公证（2026-10-04 口径：可零成本起步，**自签证书对分发无意义**）

**先回答"能否自签"**：代码签名证书自签≠免警告——用户机器不信任自建根，
SmartScreen/Gatekeeper 的提示与不签名完全一样；macOS 公证（notarytool）只认
Apple 签发的 Developer ID，自签根本走不通。因此签名策略按成本分三档：

| 档 | 做法 | 用户所见 | 成本 |
|---|---|---|---|
| 起步（现在） | **不签名分发** | Win：SmartScreen「仍要运行」；mac：右键打开/xattr -cr 绕 Gatekeeper | 0 |
| Windows 转正 | **Azure Trusted Signing**（无硬件令牌，个人可申） | 无「未知发布者」告警 | $9.99/月 |
| macOS 转正 | **Apple Developer**（Developer ID + notarize，绕不开） | 双击直开 | $99/年 |

- 起步期缓解：Windows 提交微软误报分析降低 Defender 命中（PyInstaller 产物
  误报是已知问题）；macOS 可发 zip 并附一行 `xattr -cr` 引导。
- **更新通道完整性不依赖购买证书**：electron-updater 的 latest.yml 用构建时
  自生成的 SHA512 密钥签名（`electron-builder` 自动管理），与代码签名证书无关。
- License 验签同样自管：keypair 由 `backend/scripts/license_tools.py keygen`
  生成（Ed25519），公钥构建时注入 `LICENSE_PUBLIC_KEY`，私钥离线保管——
  这部分"自签"是完全正当且零成本的。
- 转正后配置：Win `win.certificateSubjectName`/Azure；mac `mac.identity` +
  `notarize: true`，且 **sidecar 二进制必须与主程序同签**（afterSign 钩子对
  `resources/meloyu-backend/**` 逐个 `codesign` 后统一 `notarytool submit`）。

## 自动更新

- 更新源：官网静态目录（P3，`https://meloyu.com/updates/`，Dokploy/nginx 或 R2 CDN）。
- 打包机注入 `MELOYU_UPDATE_URL` 启用 electron-updater（generic provider），
  `latest.yml` 由 electron-builder 随包产出，直接上传更新目录即可。
- 更新权利随 License 验签放行（方案 §4.3：终身授权含全部版本更新）。

## 已知边界

- 本地大模型（ACE-Step / MusicGen 权重）不随包分发，首启后经模型中心
  「本地组件」区按需下载（组件中心 UI 已交付：许可/体积/显存如实标注，
  下载复用 ModelOp 进度管线）。
- 云通道（Suno 网关 / Replicate）为 BYOK：用户在模型中心自配 Key（桌面本地
  档案 is_admin，配置面即面向用户）。
- macOS 本地推理以 MusicGen(CPU)+内置引擎保底；ACE-Step mac 构建未验证。
