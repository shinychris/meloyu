/**
 * Meloyu Desktop — Electron 主进程（P2，2026-10-03 定位转型）。
 *
 * 职责：
 * - 单实例锁（第二实例聚焦已有窗口，转发命令行深度链接）
 * - 选取空闲回环端口 → 拉起后端 sidecar（FastAPI 单体，APP_MODE=desktop）
 * - 健康检查就绪后加载 http://127.0.0.1:<port>（sidecar 同源托管前端 SPA，
 *   HttpOnly Cookie 刷新机制原样工作）
 * - 深度链接 meloyu://activate?key=... → 主进程代为激活 → 跳激活页
 * - 麦克风权限（哼唱/人声克隆 getUserMedia）
 * - 自动更新（electron-updater + generic 更新源；未配置 UPDATE_URL 时静默跳过）
 * - 退出时优雅关停 sidecar（SIGTERM → 3s 强杀）
 *
 * 安全基线：contextIsolation=true、nodeIntegration=false、http 仅限回环 sidecar。
 */
'use strict'

const { app, BrowserWindow, Menu, shell, session, dialog } = require('electron')
const { spawn } = require('node:child_process')
const net = require('node:net')
const path = require('node:path')
const fs = require('node:fs')
const http = require('node:http')

const IS_DEV = !app.isPackaged
const DEV_BACKEND_URL = process.env.MELOYU_DEV_BACKEND || 'http://127.0.0.1:8000'

let mainWindow = null
let sidecar = null          // ChildProcess
let sidecarPort = 0
let sidecarBase = ''
let quitting = false

// ---------- 单实例锁 ----------
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
}

// ---------- 深度链接 meloyu:// ----------
app.setAsDefaultProtocolClient('meloyu')
handleDeepLinkArgs(process.argv)

function extractLinkFromArgv(argv) {
  for (const arg of argv) {
    const m = /^meloyu:\/\/activate\?(.+)$/i.exec(arg)
    if (m) return new URLSearchParams(m[1])
  }
  return null
}

/** 深度链接两种形态（激活邮件可任选其一）：
 *  meloyu://activate?account=..&code=..  —— 在线激活（主流程）
 *  meloyu://activate?key=..              —— 离线激活（完整授权密钥） */
function handleDeepLinkArgs(argv) {
  const params = extractLinkFromArgv(argv)
  if (!params || !sidecarBase) return
  const account = params.get('account')
  const code = params.get('code')
  const key = params.get('key')
  const path = account && code ? '/api/v1/licenses/activate-online' : '/api/v1/licenses/activate'
  const body = account && code ? { account, code } : { license_key: key }
  if (!body.license_key && !(body.account && body.code)) return
  // 主进程代为激活（免手动粘贴），完成后跳「定价与激活」页展示结果
  const req = http.request(
    `${sidecarBase}${path}`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' } },
    () => {
      if (mainWindow) mainWindow.loadURL(`${sidecarBase}/#/pricing`).catch(() => {})
    },
  )
  req.on('error', () => {
    if (mainWindow) mainWindow.loadURL(`${sidecarBase}/#/pricing`).catch(() => {})
  })
  req.end(JSON.stringify(body))
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
function sidecarCommand() {
  if (IS_DEV) {
    // dev：直接用 backend venv 的 python 起 uvicorn（热改代码即重启壳生效）
    const py = process.platform === 'win32'
      ? path.resolve(__dirname, '../../backend/.venv/Scripts/python.exe')
      : path.resolve(__dirname, '../../backend/.venv/bin/python')
    return { cmd: py, args: ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1'] }
  }
  const dir = path.join(process.resourcesPath, 'meloyu-backend')
  const exe = process.platform === 'win32' ? 'desktop_runner.exe' : 'desktop_runner'
  return { cmd: path.join(dir, exe), args: [], cwd: dir }
}

function startSidecar() {
  const { cmd, args, cwd } = sidecarCommand()
  const userDataData = path.join(app.getPath('userData'), 'data')
  fs.mkdirSync(userDataData, { recursive: true })
  const env = {
    ...process.env,
    APP_MODE: 'desktop',
    MELOYU_PORT: String(sidecarPort),
    DATA_DIR: userDataData,
    ENV: 'dev',               // 桌面形态沿用 dev 语义（无生产断言；无固定密码播种）
    ALLOW_LAN_DEV: 'false',
    // 前端静态目录：dev=仓库 frontend/dist；打包=resources/web
    DESKTOP_STATIC_DIR: IS_DEV
      ? path.resolve(__dirname, '../../frontend/dist')
      : path.join(process.resourcesPath, 'web'),
  }
  sidecar = spawn(cmd, [...args, ...(!IS_DEV ? [] : [])], {
    cwd: cwd || path.resolve(__dirname, '../../backend'),
    env,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  sidecar.stdout.on('data', (d) => process.stdout.write(`[sidecar] ${d}`))
  sidecar.stderr.on('data', (d) => process.stderr.write(`[sidecar] ${d}`))
  sidecar.on('exit', (code) => {
    sidecar = null
    if (!quitting) {
      dialog.showErrorBox(
        'Meloyu',
        `Backend exited unexpectedly (code ${code}). The app will now close.`,
      )
      app.quit()
    }
  })
}

function stopSidecar() {
  if (!sidecar) return Promise.resolve()
  const child = sidecar
  sidecar = null
  return new Promise((resolve) => {
    const killTimer = setTimeout(() => {
      try { child.kill('SIGKILL') } catch { /* already gone */ }
      resolve()
    }, 3000)
    child.once('exit', () => { clearTimeout(killTimer); resolve() })
    try { child.kill() } catch { /* already gone */ }
  })
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
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  })
  mainWindow.once('ready-to-show', () => mainWindow.show())
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(LOADING_HTML)}`)

  // 外链一律走系统浏览器（官网购买/帮助文档）
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://127.0.0.1:') || url.startsWith('meloyu://')) return { action: 'allow' }
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.on('closed', () => { mainWindow = null })
}

// ---------- 权限（麦克风：哼唱/人声克隆） ----------
function installPermissionHandlers() {
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    const allowed = new Set(['media', 'audioCapture', 'pointerLock', 'fullscreen'])
    callback(allowed.has(permission))
  })
}

// ---------- 自动更新（签名后启用；未配置 UPDATE_URL 静默跳过） ----------
function setupAutoUpdater() {
  const updateUrl = process.env.MELOYU_UPDATE_URL || ''
  if (IS_DEV || !updateUrl) return
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
  createWindow()

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
    if (mainWindow) await mainWindow.loadURL(`${sidecarBase}/`)
  } catch (e) {
    dialog.showErrorBox('Meloyu', `Failed to start local backend: ${e.message}`)
    app.quit()
    return
  }
  setupAutoUpdater()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow().catch?.(() => {})
    else if (mainWindow) mainWindow.show()
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
      { role: 'reload' },
      { role: 'toggleDevTools' },
      { type: 'separator' },
      { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' },
      { role: 'togglefullscreen' },
    ],
  },
]
Menu.setApplicationMenu(Menu.buildFromTemplate(template))
