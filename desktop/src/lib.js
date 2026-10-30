/**
 * 主进程纯函数抽离（node:test 可测，不依赖 Electron API）：
 * 深度链接解析与派发决策 / 外链与权限白名单 / 激活响应解析 /
 * 更新源校验 / CSP 策略。main.js 消费。
 */
'use strict'

/** 从命令行参数中提取 meloyu://activate 深链参数（单实例转发/冷启动两处入口） */
function extractLinkFromArgv(argv) {
  for (const arg of argv) {
    const m = /^meloyu:\/\/activate\?(.+)$/i.exec(arg)
    if (m) return new URLSearchParams(m[1])
  }
  return null
}

/**
 * 深链参数 → 激活请求（2026-10-04 激活码口径，两种形态任选其一）：
 *  meloyu://activate?account=..&code=..  在线激活（主流程：portal 兑换）
 *  meloyu://activate?key=..              离线激活（完整签名密钥备用）
 * account+code 优先；两者皆缺返回 null（非激活深链，忽略）。
 */
function activateRequestFromParams(params) {
  if (!params) return null
  const account = params.get('account')
  const code = params.get('code')
  const key = params.get('key')
  if (account && code) {
    return { path: '/api/v1/licenses/activate-online', body: { account, code } }
  }
  if (key) {
    return { path: '/api/v1/licenses/activate', body: { license_key: key } }
  }
  return null
}

/**
 * 深链派发决策（评审 F-DT-01：深链冷启动静默丢失修复）。
 * 冷启动时模块顶层解析 argv 时 sidecarBase 尚未就绪，激活请求必须先挂起，
 * 待健康检查通过后重放；sidecarBase 就绪则立即派发；非激活深链忽略。
 * main.js 侧「后到的挂起请求覆盖先到的」由此函数 + pendingDeepLink 变量实现。
 */
function planDeepLink(request, sidecarBase) {
  if (!request) return { action: 'ignore' }
  return sidecarBase ? { action: 'dispatch' } : { action: 'park' }
}

// ---------- 外链白名单（评审 F-DT-04） ----------

/** 回环 host 判定（http:// 仅放行本机；IPv6 字面量去方括号后比较） */
function isLoopbackHost(hostname) {
  const h = String(hostname || '').toLowerCase().replace(/^\[|\]$/g, '')
  return h === '127.0.0.1' || h === 'localhost' || h === '::1'
}

/**
 * openExternal 白名单：仅 https:（官网/帮助文档等外部页面）与 http: 限定
 * 回环 host 才允许交给系统浏览器；file:/smb:/javascript: 等其余协议一律拒绝
 * （window.open 到任意 scheme 不再无条件透传给 OS）。
 */
function isExternalOpenAllowed(rawUrl) {
  let u
  try { u = new URL(rawUrl) } catch { return false }
  if (u.protocol === 'https:') return true
  if (u.protocol === 'http:') return isLoopbackHost(u.hostname)
  return false
}

/**
 * 新窗口分类（评审 F-DT-03/04）：
 * - allow：sidecarBase 前缀（本机 SPA 自身弹窗；由任意回环端口收紧为同源前缀）
 * - external：白名单外链 → 调用方转交系统浏览器
 * - deny：其余一律拒绝（不打开也不外抛）
 */
function classifyWindowOpen(url, sidecarBase) {
  if (sidecarBase && url.startsWith(sidecarBase)) return 'allow'
  if (isExternalOpenAllowed(url)) return 'external'
  return 'deny'
}

// ---------- 权限来源校验（评审 F-DT-05） ----------

/**
 * 权限请求判定：media/audioCapture（麦克风）仅 sidecarBase 来源
 * （details.requestingUrl）放行，其余来源拒绝；pointerLock/fullscreen 与
 * 来源无关照旧放行；其余权限一律拒绝。
 */
function isPermissionAllowed(permission, requestingUrl, sidecarBase) {
  if (permission === 'pointerLock' || permission === 'fullscreen') return true
  if (permission !== 'media' && permission !== 'audioCapture') return false
  return !!sidecarBase && typeof requestingUrl === 'string'
    && requestingUrl.startsWith(sidecarBase)
}

// ---------- 深链激活响应解析（评审 F-DT-14） ----------

/**
 * 激活响应解析：后端统一信封 {code, message, data, request_id}，HTTP 200 且
 * code===0 视为成功；非 200 / 非 JSON / code!==0 一律判失败并带出原因——
 * 失败不得再导航到设置页假装成功（调用方给出明确错误提示）。
 */
function parseActivationResponse(statusCode, bodyText) {
  let body = null
  try { body = JSON.parse(bodyText) } catch { /* 非 JSON 响应体 */ }
  const ok = statusCode === 200 && body !== null && typeof body === 'object'
    && Number(body.code) === 0
  return { ok, reason: ok ? '' : ((body && body.message) || `HTTP ${statusCode}`) }
}

// ---------- 自动更新源校验（评审 F-DT-16） ----------

/** 更新 feed 指向可执行安装包，非 https 明文可被中间人替换——必须 https 才启用 */
function isHttpsUpdateUrl(url) {
  return typeof url === 'string' && url.startsWith('https://')
}

/**
 * 应用页 CSP（方案 §6.3 承诺项，2026-10-16 补全）。
 * SPA 静态资源与全部接口同源（sidecar 回环），故 default-src 'self'；
 * style 'unsafe-inline' = React 内联样式；Google Fonts 为 frontend/index.html
 * 既有外链（离线时请求失败自然回退系统字体，不阻断渲染）。
 */
const CSP_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' data: https://fonts.gstatic.com",
  "img-src 'self' data: blob:",
  "media-src 'self' blob:",
  "connect-src 'self'",
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join('; ')

module.exports = {
  extractLinkFromArgv,
  activateRequestFromParams,
  planDeepLink,
  isLoopbackHost,
  isExternalOpenAllowed,
  classifyWindowOpen,
  isPermissionAllowed,
  parseActivationResponse,
  isHttpsUpdateUrl,
  CSP_POLICY,
}
