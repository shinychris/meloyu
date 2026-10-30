# Meloyu Desktop（Electron 壳）

> 2026-10-03 定位转型（P2）：SaaS → 桌面软件买断制。壳 = Electron 主进程 +
> FastAPI sidecar（`APP_MODE=desktop`，SQLite + 免登录 + 试用期/License 激活）+
> 同源托管的前端 SPA（`frontend/dist`）。方案：`docs/06-商业化/2026-10-03-定位调整方案-SaaS转桌面买断制.md`。

## 架构

```
Electron 主进程（src/main.js）
 ├─ 单实例锁 + meloyu://activate 深度链接（account+code 在线 / key 离线备用，
 │  纯函数抽 src/lib.js 供 node:test 覆盖；冷启动先挂起、sidecar 就绪后重放，
 │  macOS 走 open-url、Windows/Linux 走第二实例 argv 转发）
 ├─ pickFreePort → spawn sidecar（127.0.0.1 随机端口；dev uvicorn 同端口）
 ├─ 健康检查 /api/v1/system/health → loadURL http://127.0.0.1:<port>
 ├─ 麦克风权限（哼唱/人声克隆，仅 sidecar 同源来源放行）
 ├─ 导航/新窗口守卫 + openExternal 白名单（https / 回环 http 之外一律拒绝）
 ├─ CSP 响应头（同源默认 + Google Fonts 白名单，src/lib.js CSP_POLICY）
 ├─ 托盘（Show/Quit）+ 应用图标（build/icon.{png,ico}，品牌方格音符标）
 └─ 退出优雅关停 sidecar（POST /_sidecar/shutdown → SIGTERM 3s 宽限 →
    Windows taskkill /T 树杀 / POSIX SIGKILL 兜底）

sidecar（backend 打包，scripts/desktop_runner.py）
 ├─ APP_MODE=desktop：SQLite、本地档案免登录、14 天试用 + License 激活
 ├─ 首启生成实例密钥 ~/Meloyu/.secrets.json（jwt + BYOK Key 落库加密）
 ├─ Host 头校验（仅 127.0.0.1/localhost + 本端口，防 DNS rebinding）+ 摘除
 │  /api/docs 与 CORS（桌面成品收敛 dev 语义面；dev 直启 uvicorn 不经过
 │  desktop_runner，无这些收敛也不强制）
 ├─ POST /_sidecar/shutdown：壳退出时 HTTP 优雅关停（仅 MELOYU_PORT 注入时注册）
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
# 单测（深链解析/CSP 纯函数，node 内建 runner）
cd desktop && npm test
```

## 打包发布（按序三步；v0.16.2 Windows 链路实跑验证通过）

```bash
# ① sidecar（backend/dist-backend/meloyu-backend/）
desktop\sidecar\build-sidecar.cmd        # Windows
desktop/sidecar/build-sidecar.sh         # macOS
# 注意：--specpath scripts 使相对路径以 scripts/ 为基准（app 包须写作 ..\app）

# ② 前端
cd frontend && npm run build

# ③ 三方许可声明（法务交付标配；每次发布前重跑）
cd desktop && npm run notices            # → THIRD-PARTY-NOTICES.md（随包分发）

# ④ 壳（desktop/release/ 产出安装包）
cd desktop && npm run dist:win           # NSIS x64
cd desktop && npm run dist:mac           # dmg arm64 + x64（需 mac 主机）
```

图标已入库（`build/icon.ico`、`build/icon.png`，electron-builder 直接引用，
新 clone 无需预生成步骤）；品牌重制时用
`python desktop/scripts/gen-icon.py` 重新生成（依赖 Pillow，见脚本头注释）。

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
- **更新通道完整性现状（2026-10-27 更正）**：electron-updater 的 `latest.yml`
  中的 sha512 只是**构建产物校验和（checksum），不是签名**——它只能检测
  下载损坏，不能证明发布者身份；更新完整性当前仅由更新目录的 HTTPS 传输
  保障。**启用自动更新通道前必须先落实代码签名/公证**（Win 走 Azure
  Trusted Signing、mac 走 Developer ID + notarize，见上表转正档），
  electron-updater 拿到签名后的安装包才能完成发布者校验闭环；在那之前
  更新分发保持「官网手动下载」口径。
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
  **仅接受 `https://` 前缀**（非 https 拒绝启用并告警，防中间人替换安装包）；
  且须先落实上节代码签名/公证（见「签名与公证」更新通道完整性条目）。
- 更新权利随 License 验签放行（方案 §4.3：终身授权含全部版本更新）。

## 已知边界

- **Electron 依赖时效纪律（2026-10-27 评审 F-XC-01 起）**：桌面客户端 Chromium
  只能靠发版升级，每次发版前跑 `npm outdated` 检查 electron/electron-builder——
  不得落后官方支持窗口（最近 3 个大版本）两个大版本以上。曾因 v0.16.x 起步时
  钉 ^33 而失察，2026-10-27 评审时已落后两年（33→45 补升）。
- 本地大模型（ACE-Step / MusicGen 权重）不随包分发，首启后经模型中心
  「本地组件」区按需下载（组件中心 UI 已交付：许可/体积/显存如实标注，
  下载复用 ModelOp 进度管线）。
- 云通道（Suno 网关 / Replicate）为 BYOK：用户在模型中心自配 Key（desktop
  形态配置面显式对当前用户开放，require_admin 桌面分支；Key 经实例 Fernet
  密钥加密落库）。
- macOS 本地推理以 MusicGen(CPU)+内置引擎保底；ACE-Step mac 构建未验证；
  **macOS dmg 需在 mac 主机构建**（electron-builder 不支持跨平台 dmg）。
- EULA 待法务定稿（外部动作）：package.json license 暂为 Proprietary，
  定稿后经 nsis.license 挂载安装器许可页；THIRD-PARTY-NOTICES.md 已随包分发。

## Windows 打包已知坑（无管理员权限的机器）

- electron-builder 解压 winCodeSign 缓存时需创建 macOS 符号链接（7za 报
  「客户端没有所需的特权」，issue #4299），exe 图标嵌入（rcedit）因此中断。
  正式发布机任选其一：开启 Windows 开发者模式 / 管理员终端跑一次 / 补缓存。
  临时绕过（v0.16.2 验证构建即此法，安装包/快捷方式图标不受影响，仅 exe
  本体图标为 Electron 默认）：

```bash
npx electron-builder --win nsis -c.win.signAndEditExecutable=false
```
