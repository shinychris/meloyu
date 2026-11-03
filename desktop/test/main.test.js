/**
 * 主进程纯函数单测（node:test 内建运行器，零新增依赖）：
 *   npm test  →  node --test test/
 */
'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const {
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
} = require('../src/lib')

test('extractLinkFromArgv 提取激活深链参数', () => {
  const argv = ['Meloyu.exe', '--type=renderer', 'meloyu://activate?account=a@b.c&code=MELOYU-12345678-9ABCDEF0']
  const params = extractLinkFromArgv(argv)
  assert.equal(params.get('account'), 'a@b.c')
  assert.equal(params.get('code'), 'MELOYU-12345678-9ABCDEF0')
})

test('extractLinkFromArgv 无深链时返回 null', () => {
  assert.equal(extractLinkFromArgv(['Meloyu.exe', '--flag']), null)
  assert.equal(extractLinkFromArgv([]), null)
})

test('account+code → 在线激活（主流程，优先于 key）', () => {
  const req = activateRequestFromParams(
    new URLSearchParams('account=a@b.c&code=MELOYU-X&key=v1.fullkey'),
  )
  assert.equal(req.path, '/api/v1/licenses/activate-online')
  assert.deepEqual(req.body, { account: 'a@b.c', code: 'MELOYU-X' })
})

test('仅 key → 离线激活（完整签名密钥备用通道）', () => {
  const req = activateRequestFromParams(new URLSearchParams('key=v1.abc.sig'))
  assert.equal(req.path, '/api/v1/licenses/activate')
  assert.deepEqual(req.body, { license_key: 'v1.abc.sig' })
})

test('参数不全返回 null（account 缺 code / 全空 / null）', () => {
  assert.equal(activateRequestFromParams(new URLSearchParams('account=a@b.c')), null)
  assert.equal(activateRequestFromParams(new URLSearchParams('')), null)
  assert.equal(activateRequestFromParams(null), null)
})

// ---------- ：深链冷启动挂起/重放决策 ----------

test('planDeepLink：无有效请求 → ignore', () => {
  assert.deepEqual(planDeepLink(null, ''), { action: 'ignore' })
  assert.deepEqual(planDeepLink(null, 'http://127.0.0.1:54321'), { action: 'ignore' })
})

test('planDeepLink：sidecarBase 未就绪 → park（冷启动挂起）', () => {
  const req = activateRequestFromParams(new URLSearchParams('account=a@b.c&code=X'))
  assert.deepEqual(planDeepLink(req, ''), { action: 'park' })
})

test('planDeepLink：sidecarBase 就绪 → dispatch（立即派发）', () => {
  const req = activateRequestFromParams(new URLSearchParams('account=a@b.c&code=X'))
  assert.deepEqual(planDeepLink(req, 'http://127.0.0.1:54321'), { action: 'dispatch' })
})

// ---------- ：openExternal 白名单 ----------

test('isLoopbackHost：仅接受回环主机名（IPv6 字面量去括号）', () => {
  assert.equal(isLoopbackHost('127.0.0.1'), true)
  assert.equal(isLoopbackHost('localhost'), true)
  assert.equal(isLoopbackHost('LOCALHOST'), true)
  assert.equal(isLoopbackHost('[::1]'), true)
  assert.equal(isLoopbackHost('::1'), true)
  assert.equal(isLoopbackHost('example.com'), false)
  assert.equal(isLoopbackHost('127.0.0.1.evil.com'), false)
  assert.equal(isLoopbackHost(''), false)
})

test('isExternalOpenAllowed：https 放行，http 仅回环，其余协议拒绝', () => {
  assert.equal(isExternalOpenAllowed('https://meloyu.com/updates/'), true)
  assert.equal(isExternalOpenAllowed('https://fonts.googleapis.com'), true)
  assert.equal(isExternalOpenAllowed('http://127.0.0.1:8000/x'), true)
  assert.equal(isExternalOpenAllowed('http://localhost:5173/'), true)
  // 恶意/任意 scheme 与非回环 http 一律拒绝（file:/smb:/ftp:/javascript: 等）
  assert.equal(isExternalOpenAllowed('http://meloyu.com'), false)
  assert.equal(isExternalOpenAllowed('file:///C:/Windows/System32'), false)
  assert.equal(isExternalOpenAllowed('smb://server/share'), false)
  assert.equal(isExternalOpenAllowed('javascript:alert(1)'), false)
  assert.equal(isExternalOpenAllowed('meloyu://activate?account=a&code=b'), false)
  assert.equal(isExternalOpenAllowed('not a url'), false)
})

// ---------- ：新窗口分类 ----------

test('classifyWindowOpen：仅 sidecarBase 前缀可窗口内打开（收紧自任意回环端口）', () => {
  const base = 'http://127.0.0.1:54321'
  assert.equal(classifyWindowOpen(`${base}/#/settings`, base), 'allow')
  assert.equal(classifyWindowOpen(`${base}/api/v1/x`, base), 'allow')
  // 其他回环端口不再放行进窗口
  assert.equal(classifyWindowOpen('http://127.0.0.1:9999/', base), 'external')
  assert.equal(classifyWindowOpen('https://meloyu.com', base), 'external')
  assert.equal(classifyWindowOpen('file:///etc/passwd', base), 'deny')
  assert.equal(classifyWindowOpen('meloyu://activate?account=a&code=b', base), 'deny')
})

test('classifyWindowOpen：sidecarBase 为空时什么都不允许进窗口', () => {
  assert.equal(classifyWindowOpen('http://127.0.0.1:8000/', ''), 'external')
  assert.equal(classifyWindowOpen('file:///x', ''), 'deny')
})

// ---------- ：权限来源校验 ----------

test('isPermissionAllowed：麦克风仅 sidecarBase 来源，其余权限照旧/拒绝', () => {
  const base = 'http://127.0.0.1:54321'
  assert.equal(isPermissionAllowed('media', `${base}/#/studio`, base), true)
  assert.equal(isPermissionAllowed('audioCapture', `${base}/#/studio`, base), true)
  // 来源不是 sidecarBase（外站/空）→ 拒绝
  assert.equal(isPermissionAllowed('media', 'https://evil.example/', base), false)
  assert.equal(isPermissionAllowed('media', '', base), false)
  assert.equal(isPermissionAllowed('media', undefined, base), false)
  assert.equal(isPermissionAllowed('media', `${base}/x`, ''), false)
  // 来源无关权限照旧放行；未列权限拒绝
  assert.equal(isPermissionAllowed('fullscreen', 'https://x/', base), true)
  assert.equal(isPermissionAllowed('pointerLock', `${base}/x`, base), true)
  assert.equal(isPermissionAllowed('geolocation', `${base}/x`, base), false)
  assert.equal(isPermissionAllowed('notifications', `${base}/x`, base), false)
})

// ---------- ：激活响应解析 ----------

test('parseActivationResponse：HTTP 200 + code===0 为成功', () => {
  const r = parseActivationResponse(200, '{"code":0,"message":"ok","data":{}}')
  assert.equal(r.ok, true)
  assert.equal(r.reason, '')
})

test('parseActivationResponse：业务失败（code!==0）带出 message', () => {
  const r = parseActivationResponse(422, '{"code":40202,"message":"激活码无效"}')
  assert.equal(r.ok, false)
  assert.equal(r.reason, '激活码无效')
})

test('parseActivationResponse：非 200 / 非 JSON / 空体一律失败', () => {
  assert.equal(parseActivationResponse(500, 'Internal Server Error').ok, false)
  assert.equal(parseActivationResponse(200, '<html>boom</html>').ok, false)
  assert.equal(parseActivationResponse(200, '').ok, false)
  assert.equal(parseActivationResponse(404, null).ok, false)
  // 非 200 即使 code===0 也不算成功
  assert.equal(parseActivationResponse(500, '{"code":0}').ok, false)
})

// ---------- ：更新源校验 ----------

test('isHttpsUpdateUrl：仅 https 放行（feed 含可执行更新）', () => {
  assert.equal(isHttpsUpdateUrl('https://meloyu.com/updates/'), true)
  assert.equal(isHttpsUpdateUrl('http://meloyu.com/updates/'), false)
  assert.equal(isHttpsUpdateUrl('ftp://x'), false)
  assert.equal(isHttpsUpdateUrl(''), false)
  assert.equal(isHttpsUpdateUrl(undefined), false)
})

// ---------- CSP（原有断言保持） ----------

test('CSP：同源默认 + 脚本白名单不含通配 http + 关键收紧项在位', () => {
  assert.ok(CSP_POLICY.startsWith("default-src 'self'"))
  const scriptSrc = CSP_POLICY.match(/script-src ([^;]+)/)[1]
  assert.ok(!scriptSrc.includes('http:') && !scriptSrc.includes('https:') && !scriptSrc.includes('*'),
    `script-src 过宽：${scriptSrc}`)
  assert.ok(CSP_POLICY.includes("object-src 'none'"))
  assert.ok(CSP_POLICY.includes("frame-ancestors 'none'"))
  assert.ok(CSP_POLICY.includes('https://fonts.googleapis.com')) // index.html 既有字体外链
})
