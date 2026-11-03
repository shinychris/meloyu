/**
 * Meloyu Desktop — Electron 主进程。
 *
 * 职责：
 * - 单实例锁（第二实例聚焦已有窗口并转发命令行深度链接；锁失败分支完全隔离，
 *   不做任何协议/菜单/事件注册）
 * - 选取空闲回环端口 → 拉起后端 sidecar（FastAPI 单体，APP_MODE=desktop）
 * - 健康检查就绪后加载 http://127.0.0.1:<port>（sidecar 同源托管前端 SPA，
 *   HttpOnly Cookie 刷新机制原样工作）；冷启动收到的深链在此刻重放
 * - 深度链接 meloyu://activate?account=..&code=..（在线）/ ?key=..（离线备用）
 *   → 主进程代为激活 → 读响应结果区分提示后跳授权设置页
 * - 导航/新窗口守卫 + openExternal 白名单+ 权限来源校验
 * - sidecar 优雅退出：HTTP /_sidecar/shutdown → SIGTERM 宽限 → Windows
 *   taskkill /T 树杀兜底
 * - CSP 响应头（默认同源；Google Fonts 为既有外链白名单）
 * - 托盘（显示窗口/退出）+ 应用图标
 * - 自动更新（electron-updater + generic 更新源，仅接受 https；未配置时静默跳过）
 *
 * 安全基线：contextIsolation=true、nodeIntegration=false、http 仅限回环 sidecar。
 */
'use strict'

const { app, BrowserWindow, Menu, shell, session, dialog, Tray, nativeImage } = require('electron')
const { spawn } = require('node:child_process')
const net = require('node:net')
const path = require('node:path')
const fs = require('node:fs')
const http = require('node:http')
const {
  extractLinkFromArgv,
  activateRequestFromParams,
  planDeepLink,
  isExternalOpenAllowed,
  classifyWindowOpen,
  isPermissionAllowed,
  parseActivationResponse,
  isHttpsUpdateUrl,
  CSP_POLICY,
} = require('./lib')

const IS_DEV = !app.isPackaged
const DEV_BACKEND_URL = process.env.MELOYU_DEV_BACKEND || 'http://127.0.0.1:8000'

let mainWindow = null
let tray = null
let sidecar = null          // ChildProcess
let sidecarPort = 0
let sidecarBase = ''
let quitting = false
let pendingDeepLink = null  // 冷启动挂起的激活请求（后到覆盖先到，就绪后重放）

// ---------- 深度链接 meloyu:// ----------

function handleDeepLinkArgs(argv) {
  const req = activateRequestFromParams(extractLinkFromArgv(argv))
  const plan = planDeepLink(req, sidecarBase)
  if (plan.action === 'ignore') return
  if (plan.action === 'park') {
    // 冷启动 sidecar 未就绪：挂起待健康检查通过后重放（后到的覆盖先到的）
    pendingDeepLink = req
    return
  }
  dispatchActivation(req)
}

/** sidecar 就绪后重放挂起的激活深链（购买邮件「一键激活」冷启动不再静默丢失） */
function replayPendingDeepLink() {
  if (!pendingDeepLink || !sidecarBase) return
  const req = pendingDeepLink
  pendingDeepLink = null
  dispatchActivation(req)
}

/** mainWindow 使用前的销毁守卫 + loadURL 同步异常捕获（窗口销毁竞态） */
function safeLoad(url) {
  const win = mainWindow
  if (!win || win.isDestroyed()) return
  try {
    win.loadURL(url).catch(() => {})
  } catch { /* 窗口在导航期间被销毁 */ }
}

function activationFailed(reason) {
  // ：失败显式提示，不再导航设置页假装成功
  dialog.showMessageBox({
    type: 'error',
    title: 'Meloyu',
    message: `Activation failed: ${reason}`,
    detail: 'Open Settings → License in the app and try again, or use the full '
      + 'license key from your activation email for offline activation.',
  }).catch(() => {})
  safeLoad(`${sidecarBase}/#/settings`)
}

function dispatchActivation(req) {
  // 主进程代为激活（免手动粘贴），读响应体 ok 字段区分结果后跳授权设置分区
  // （v0.17.0 起激活/授权入口自定价页迁入 /settings）
  const r = http.request(
    `${sidecarBase}${req.path}`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' } },
    (res) => {
      const chunks = []
      res.on('data', (c) => chunks.push(c))
      res.on('end', () => {
        const { ok, reason } = parseActivationResponse(
          res.statusCode, Buffer.concat(chunks).toString('utf8'))
        if (ok) safeLoad(`${sidecarBase}/#/settings`)
        else activationFailed(reason)
      })
    },
  )
  r.on('error', () => activationFailed('network error'))
  r.end(JSON.stringify(req.body))
}

// ---------- 端口探测 ----------
function pickFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.unref()
    srv.on('error', reject)
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address()
      srv.close(() => resolve(port))
    })
  })
}

// ---------- sidecar 生命周期 ----------
function sidecarCommand(port) {
  if (IS_DEV) {
    // dev：直接用 backend venv 的 python 起 uvicorn（热改代码即重启壳生效）；
    // 端口用壳选取的空闲端口（--port 必传：uvicorn 默认 8000 会导致健康检查探测错端口）
    const py = process.platform === 'win32'
      ? path.resolve(__dirname, '../../backend/.venv/Scripts/python.exe')
      : path.resolve(__dirname, '../../backend/.venv/bin/python')
    return {
      cmd: py,
      args: ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(port)],
    }
  }
  const dir = path.join(process.resourcesPath, 'meloyu-backend')
  const exe = process.platform === 'win32' ? 'desktop_runner.exe' : 'desktop_runner'
  return { cmd: path.join(dir, exe), args: [], cwd: dir }
}

function startSidecar() {
  const { cmd, args, cwd } = sidecarCommand(sidecarPort)
  const userDataData = path.join(app.getPath('userData'), 'data')
  fs.mkdirSync(userDataData, { recursive: true })
  const env = {
    ...process.env,
    //  调研结论（2026-10-27）：app_mode=desktop 即现值（pydantic 的
    // app_mode 字段读 APP_MODE env）——license gate/试用闸门/本地档案链路照常
    // 生效；数据路径由 DATA_DIR 接管（config.data_path 中 data_dir 非空时优先
    // 于 desktop 默认的 ~/Meloyu，无冲突，config.py 无需改动）。
    APP_MODE: 'desktop',
    MELOYU_PORT: String(sidecarPort),
    DATA_DIR: userDataData,
    // ENV=dev 为刻意保留的「desktop 档」leniency：桌面形态无强随机密钥/PG，
    // 生产启动断言不适用；dev 语义残留面（api/docs、CORS）由 desktop_runner.py
    // 在桌面专属入口收敛（见 backend/scripts/desktop_runner.py）
    ENV: 'dev',
    ALLOW_LAN_DEV: 'false',
    // 前端静态目录：dev=仓库 frontend/dist；打包=resources/web
    DESKTOP_STATIC_DIR: IS_DEV
      ? path.resolve(__dirname, '../../frontend/dist')
      : path.join(process.resourcesPath, 'web'),
  }
  sidecar = spawn(cmd, args, {
    cwd: cwd || path.resolve(__dirname, '../../backend'),
    env,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  sidecar.stdout.on('data', (d) => process.stdout.write(`[sidecar] ${d}`))
  sidecar.stderr.on('data', (d) => process.stderr.write(`[sidecar] ${d}`))
  // ：spawn 失败（ENOENT 等）此前变未捕获异常 + 等满 30s 健康检查
  // 超时——补 error 监听，与 exit 共用清理/退出逻辑，失败即刻可见
  sidecar.on('exit', (code) => sidecarDied(`exited unexpectedly (code ${code})`))
  sidecar.on('error', (err) => sidecarDied(`failed to start: ${err.message}`))
}

/** sidecar 异常死亡共用路径：提示 + 退出（quitting 中静默，交给退出流程） */
function sidecarDied(reason) {
  if (!sidecar) return // 已被 stopSidecar 收管或已报告过（error 后可能仍发 exit）
  sidecar = null
  if (!quitting) {
    dialog.showErrorBox('Meloyu', `Backend ${reason}. The app will now close.`)
    app.quit()
  }
}

// ---------- sidecar 优雅退出 ----------
const SHUTDOWN_TIMEOUT_MS = 2500  // HTTP 优雅关停请求等待
const KILL_GRACE_MS = 3000        // 信号后宽限
const KILL_WAIT_MS = 2000         // 强杀后等待

/** 请求 desktop_runner 注册的 /_sidecar/shutdown（置 uvicorn should_exit，
 *  完成在途请求后退出，防 SQLite 写入中途被杀）；dev 直启 uvicorn 无此路由
 *  → 404/网络错误，走信号兜底 */
function requestSidecarShutdown(base) {
  return new Promise((resolve) => {
    const req = http.request(`${base}/_sidecar/shutdown`, { method: 'POST' }, (res) => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.setTimeout(SHUTDOWN_TIMEOUT_MS, () => { req.destroy(); resolve(false) })
    req.on('error', () => resolve(false))
    req.end()
  })
}

function waitExit(child, ms) {
  return new Promise((resolve) => {
    if (child.exitCode !== null || child.signalCode !== null) { resolve(); return }
    const timer = setTimeout(() => { child.removeListener('exit', onExit); resolve() }, ms)
    const onExit = () => { clearTimeout(timer); resolve() }
    child.once('exit', onExit)
  })
}

/** 硬杀兜底（退出失败路径）：Windows 用 taskkill /T 连带子进程树——sidecar
 *  可能拉起推理子进程，kill 只及直接子进程会留孤儿；POSIX 用 SIGKILL */
function hardKill(child) {
  try {
    if (process.platform === 'win32') {
      if (child.pid) {
        spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'],
          { windowsHide: true, stdio: 'ignore' })
      }
    } else {
      child.kill('SIGKILL')
    }
  } catch { /* already gone */ }
}

function stopSidecar() {
  if (!sidecar) return Promise.resolve()
  const child = sidecar
  const base = sidecarBase
  sidecar = null
  return (async () => {
    // ① HTTP 优雅关停（桌面 sidecar 专属路由）；不可用（dev 404/已死）→ 信号兜底
    const graceful = base ? await requestSidecarShutdown(base) : false
    if (!graceful) { try { child.kill() } catch { /* already gone */ } }
    // ② 宽限期后强杀
    await waitExit(child, KILL_GRACE_MS)
    if (child.exitCode === null && child.signalCode === null) {
      hardKill(child)
      await waitExit(child, KILL_WAIT_MS)
    }
  })()
}

// ---------- 健康检查 ----------
function waitUntilReady(base, timeoutMs = 30000) {
  const started = Date.now()
  return new Promise((resolve, reject) => {
    const probe = () => {
      const req = http.get(`${base}/api/v1/system/health`, (res) => {
        res.resume()
        if (res.statusCode === 200) resolve()
        else retry()
      })
      req.on('error', retry)
      req.setTimeout(2000, () => { req.destroy(); retry() })
    }
    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        reject(new Error(`backend not ready within ${timeoutMs}ms`))
        return
      }
      setTimeout(probe, 300)
    }
    probe()
  })
}

// ---------- 窗口 ----------
const LOADING_HTML = `<!doctype html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;height:100%;background:#0d0f10;color:#8be9c0;
  font-family:ui-monospace,Consolas,monospace;display:flex;align-items:center;
  justify-content:center;flex-direction:column;gap:12px}
  .logo{font-size:28px;font-weight:800;letter-spacing:.18em}
  .bar{width:180px;height:3px;background:#1d2124;overflow:hidden}
  .bar i{display:block;height:100%;width:40%;background:#8be9c0;
  animation:s 1.1s ease-in-out infinite alternate;margin-left:-40%}
  @keyframes s{to{margin-left:100%}}
</style></head><body>
<div class="logo">MELOYU</div><div class="bar"><i></i></div>
<div style="font-size:12px;opacity:.6">starting local studio…</div>
</body></html>`

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1080,
    minHeight: 700,
    backgroundColor: '#0d0f10',
    autoHideMenuBar: process.platform !== 'darwin',
    show: false,
    // win/linux 任务栏/窗口图标（mac 走 Dock 的 .icns/App 图标）
    ...(process.platform !== 'darwin' ? { icon: trayIconPath() } : {}),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  })
  mainWindow.once('ready-to-show', () => mainWindow.show())
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(LOADING_HTML)}`)
    .catch(() => {})

  // 导航守卫：SPA 内 location.href 指向非 sidecarBase 的导航
  // 一律拦下——任意页面不得被载入主窗口（绕过 CSP 且可请求麦克风）；
  // 白名单外链转交系统浏览器
  mainWindow.webContents.on('will-navigate', (e, url) => {
    if (sidecarBase && url.startsWith(sidecarBase)) return
    e.preventDefault()
    if (isExternalOpenAllowed(url)) shell.openExternal(url).catch(() => {})
  })

  // 新窗口：仅同源前缀可在窗口内打开；白名单外链走系统
  // 浏览器；其余（file:/smb:/自定义协议等）一律拒绝
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    const kind = classifyWindowOpen(url, sidecarBase)
    if (kind === 'allow') return { action: 'allow' }
    if (kind === 'external') shell.openExternal(url).catch(() => {})
    return { action: 'deny' }
  })

  mainWindow.on('closed', () => { mainWindow = null })
}

// ---------- 权限（麦克风：哼唱/人声克隆） ----------
function installPermissionHandlers() {
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback, details) => {
    // ：media/audioCapture 仅 sidecarBase 来源（requestingUrl）
    // 放行，其余来源拒绝——麦克风不外借给导航守卫漏进来的页面
    callback(isPermissionAllowed(permission, details?.requestingUrl, sidecarBase))
  })
}

// ---------- CSP（sidecar 回环页面的内容安全策略） ----------
function installCsp() {
  // 只作用于回环 sidecar 的响应；data: 装载页（启动 loading）无响应头，不受影响
  session.defaultSession.webRequest.onHeadersReceived(
    { urls: ['http://127.0.0.1:*/*'] },
    (details, callback) => {
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          'Content-Security-Policy': [CSP_POLICY],
        },
      })
    },
  )
}

// ---------- 托盘（窗口/托盘/菜单） ----------
function trayIconPath() {
  return IS_DEV
    ? path.join(__dirname, '../build/icon.png')
    : path.join(process.resourcesPath, 'icon.png')
}

function createTray() {
  const iconPath = trayIconPath()
  if (!fs.existsSync(iconPath)) return // 图标缺失不阻断启动（构建产物异常时兜底）
  tray = new Tray(nativeImage.createFromPath(iconPath))
  tray.setToolTip('Meloyu')
  const show = () => {
    if (!mainWindow) return
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
  }
  const menu = Menu.buildFromTemplate([
    { label: 'Show Meloyu', click: show },
    { type: 'separator' },
    { label: 'Quit Meloyu', click: () => app.quit() },
  ])
  tray.setContextMenu(menu)
  tray.on('click', show)
}

// ---------- 自动更新（签名后启用；未配置 UPDATE_URL 静默跳过） ----------
function setupAutoUpdater() {
  const updateUrl = process.env.MELOYU_UPDATE_URL || ''
  if (IS_DEV || !updateUrl) return
  if (!isHttpsUpdateUrl(updateUrl)) {
    // ：feed 含可执行更新，非 https 明文可被中间人替换——拒绝启用
    console.warn('[meloyu] MELOYU_UPDATE_URL must start with https:// — auto-update disabled')
    return
  }
  try {
    const { autoUpdater } = require('electron-updater')
    autoUpdater.setFeedURL({ provider: 'generic', url: updateUrl })
    autoUpdater.checkForUpdatesAndNotify().catch(() => { /* 离线静默 */ })
    setInterval(() => autoUpdater.checkForUpdatesAndNotify().catch(() => {}), 6 * 3600 * 1000)
  } catch { /* electron-updater 未装（dev）*/ }
}

// ---------- App 生命周期 ----------
app.whenReady().then(async () => {
  installPermissionHandlers()
  installCsp()
  createWindow()
  createTray()

  if (IS_DEV && process.env.MELOYU_DEV_SIDECAR !== '1') {
    // dev 直连本机已起的 uvicorn（vite proxy 同款拓扑）
    sidecarBase = DEV_BACKEND_URL
  } else {
    sidecarPort = await pickFreePort()
    sidecarBase = `http://127.0.0.1:${sidecarPort}`
    startSidecar()
  }

  try {
    await waitUntilReady(sidecarBase)
    if (mainWindow && !mainWindow.isDestroyed()) await mainWindow.loadURL(`${sidecarBase}/`)
  } catch (e) {
    dialog.showErrorBox('Meloyu', `Failed to start local backend: ${e.message}`)
    app.quit()
    return
  }
  // ：健康检查通过（sidecarBase 就绪）后重放冷启动挂起的激活深链
  replayPendingDeepLink()
  setupAutoUpdater()

  // createWindow 同步返回 undefined，原 `createWindow().catch?.(...)`
  // 对 undefined 取 .catch 必崩 TypeError
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
    else mainWindow?.show()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', async (e) => {
  if (quitting) return
  quitting = true
  if (sidecar) {
    e.preventDefault()
    await stopSidecar()
    app.quit()
  }
})

// 基础菜单（mac 需要 About 项；win 菜单栏自动隐藏）
// ：reload/toggleDevTools 仅 dev 注入，生产构建不暴露调试入口
const template = [
  ...(process.platform === 'darwin' ? [{
    label: app.name,
    submenu: [
      { role: 'about' },
      { type: 'separator' },
      { role: 'hide' }, { role: 'hideOthers' },
      { type: 'separator' },
      { role: 'quit' },
    ],
  }] : []),
  {
    label: 'View',
    submenu: [
      ...(IS_DEV ? [{ role: 'reload' }, { role: 'toggleDevTools' }, { type: 'separator' }] : []),
      { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' },
      { role: 'togglefullscreen' },
    ],
  },
]

// ---------- 单实例锁（失败分支完全隔离） ----------
// 第二实例仅退出，不做协议注册/菜单/事件挂载；全部注册收敛进 gotLock 分支
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', (_e, argv) => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.focus()
    }
    handleDeepLinkArgs(argv)
  })
  // macOS 深链经 open-url 送达（含冷启动与第二实例场景：系统统一转交第一实例）
  app.on('open-url', (e, url) => {
    e.preventDefault()
    handleDeepLinkArgs([url])
  })

  app.setAsDefaultProtocolClient('meloyu')
  handleDeepLinkArgs(process.argv)

  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
}
