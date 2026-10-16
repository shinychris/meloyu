/**
 * 主进程纯函数抽离（node:test 可测，不依赖 Electron API）：
 * 深度链接解析 / 激活请求构建 / CSP 策略。main.js 消费。
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

module.exports = { extractLinkFromArgv, activateRequestFromParams, CSP_POLICY }
