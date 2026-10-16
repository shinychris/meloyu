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

test('CSP：同源默认 + 脚本白名单不含通配 http + 关键收紧项在位', () => {
  assert.ok(CSP_POLICY.startsWith("default-src 'self'"))
  const scriptSrc = CSP_POLICY.match(/script-src ([^;]+)/)[1]
  assert.ok(!scriptSrc.includes('http:') && !scriptSrc.includes('https:') && !scriptSrc.includes('*'),
    `script-src 过宽：${scriptSrc}`)
  assert.ok(CSP_POLICY.includes("object-src 'none'"))
  assert.ok(CSP_POLICY.includes("frame-ancestors 'none'"))
  assert.ok(CSP_POLICY.includes('https://fonts.googleapis.com')) // index.html 既有字体外链
})
