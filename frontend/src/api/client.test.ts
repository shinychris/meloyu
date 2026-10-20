import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  AxiosError,
  type AxiosAdapter,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios'
import { apiGet, apiPost, ApiError, http } from './client'
import { useToastStore } from '../stores/toast'

/** 用自定义 adapter 直接驱动拦截器链，验证解包 / 业务错误 / toast 行为 */
function mockAdapter(status: number, body: unknown): AxiosAdapter {
  return (config: InternalAxiosRequestConfig) =>
    Promise.resolve({
      data: body,
      status,
      statusText: 'ok',
      headers: {},
      config,
    } as AxiosResponse)
}

/** 模拟真实 http adapter 的行为：非 2xx 直接 reject AxiosError */
function mockErrorAdapter(status: number, body: unknown): AxiosAdapter {
  return (config: InternalAxiosRequestConfig) =>
    Promise.reject(
      new AxiosError('Request failed', AxiosError.ERR_BAD_RESPONSE, config, undefined, {
        data: body,
        status,
        statusText: '',
        headers: {},
        config,
      } as AxiosResponse),
    )
}

/** node 测试环境的 localStorage / window 替身（client.ts 刷新与踢登录路径依赖） */
function stubBrowser(): { store: Map<string, string> } {
  const store = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  })
  vi.stubGlobal('window', { location: { hash: '' } })
  return { store }
}

/** 当前（stub 后的）window.location.hash */
function currentHash(): string {
  return (globalThis as { window: { location: { hash: string } } }).window.location.hash
}

afterEach(() => {
  useToastStore.setState({ toasts: [] })
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  delete http.defaults.adapter
})

describe('api/client 统一封装', () => {
  it('code=0 时解包返回 data', async () => {
    http.defaults.adapter = mockAdapter(200, {
      code: 0,
      message: 'ok',
      data: { balance: 2468 },
      request_id: 'abc',
    })
    const data = await apiGet<{ balance: number }>('/credits/balance')
    expect(data).toEqual({ balance: 2468 })
  })

  it('code!=0 抛 ApiError 并 toast message', async () => {
    http.defaults.adapter = mockAdapter(402, {
      code: 40201,
      message: '积分不足：需 12，余额 3',
      data: null,
      request_id: 'abc',
    })
    await expect(apiPost('/generations', {})).rejects.toMatchObject({
      code: 40201,
      message: '积分不足：需 12，余额 3',
    })
    expect(useToastStore.getState().toasts.some((t) => t.message.includes('积分不足'))).toBe(true)
  })

  it('40203（试用到期未激活）toast 引导文案并跳系统设置的授权分区', async () => {
    stubBrowser()
    http.defaults.adapter = mockAdapter(402, {
      code: 40203,
      message: '试用期已结束：请输入 License Key 激活终身授权',
      data: null,
      request_id: 'abc',
    })
    await expect(apiPost('/generations', {})).rejects.toMatchObject({ code: 40203 })
    // v0.17.0：激活迁入 /settings（系统设置 · 授权分区）
    expect(currentHash()).toBe('#/settings')
    expect(useToastStore.getState().toasts.some((t) => t.message.includes('试用期'))).toBe(true)
  })

  it('HTTP 500 且无包裹体时给通用文案并抛 ApiError', async () => {
    http.defaults.adapter = mockErrorAdapter(500, 'internal crash')
    const err = await apiGet('/works').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).code).toBe(50001)
    expect(useToastStore.getState().toasts.length).toBe(1)
  })

  it('包裹体错误走 rejected 分支时同样解出 code/message', async () => {
    http.defaults.adapter = mockErrorAdapter(404, {
      code: 40401,
      message: '资源不存在',
      data: null,
      request_id: 'abc',
    })
    const err = await apiGet('/works/none').catch((e: unknown) => e)
    expect((err as ApiError).code).toBe(40401)
    expect((err as ApiError).message).toBe('资源不存在')
  })
})

/* ============ 40102 → /auth/refresh（v0.13.0：凭 HttpOnly Cookie 刷新）→ 重放原请求一次 ============ */

const envelope = (code: number, data: unknown = null, message = 'ok') => ({
  code,
  message,
  data,
  request_id: 't',
})

describe('api/client 40102 静默刷新', () => {
  it('40102 时凭 Cookie 刷新换新 access 并重放原请求（携带新 Bearer）', async () => {
    const { store } = stubBrowser()
    store.set('meloyu:token', 'old-access')

    let refreshCalls = 0
    http.defaults.adapter = (config) => {
      const url = config.url ?? ''
      const auth = String(config.headers?.Authorization ?? '')
      if (url.includes('/auth/refresh')) {
        refreshCalls += 1
        // v0.13.0：refresh 凭据在 HttpOnly Cookie 中，请求体不再携带
        expect(config.data).toBe('{}')
        return Promise.resolve({
          data: envelope(0, {
            access_token: 'new-access',
            token_type: 'Bearer',
            expires_in: 86400,
          }),
          status: 200,
          statusText: 'ok',
          headers: {},
          config,
        } as AxiosResponse)
      }
      // 业务请求：旧 token → 40102；新 token → 成功
      if (auth.includes('old-access')) {
        return Promise.resolve({
          data: envelope(40102, null, 'token expired'),
          status: 401,
          statusText: '',
          headers: {},
          config,
        } as AxiosResponse)
      }
      return Promise.resolve({
        data: envelope(0, { items: ['ok'] }),
        status: 200,
        statusText: 'ok',
        headers: {},
        config,
      } as AxiosResponse)
    }

    const data = await apiGet<{ items: string[] }>('/works')
    expect(data).toEqual({ items: ['ok'] })
    expect(refreshCalls).toBe(1)
    // 新 access 已落本地；refresh 不落 localStorage（HttpOnly Cookie 域）
    expect(store.get('meloyu:token')).toBe('new-access')
    expect(store.get('meloyu:refresh-token')).toBeUndefined()
    // 40102 静默处理：不 toast、不踢登录
    expect(useToastStore.getState().toasts.length).toBe(0)
    expect(currentHash()).toBe('')
  })

  it('并发两个 40102 只触发一次 /auth/refresh（单飞）', async () => {
    const { store } = stubBrowser()
    store.set('meloyu:token', 'old-access')

    let refreshCalls = 0
    http.defaults.adapter = async (config) => {
      const url = config.url ?? ''
      const auth = String(config.headers?.Authorization ?? '')
      if (url.includes('/auth/refresh')) {
        refreshCalls += 1
        // 人为延迟，保证第二个 40102 到来时刷新仍在途
        await new Promise((r) => setTimeout(r, 20))
        return {
          data: envelope(0, { access_token: 'new-access' }),
          status: 200,
          statusText: 'ok',
          headers: {},
          config,
        } as AxiosResponse
      }
      const expired = auth.includes('old-access')
      return {
        data: expired ? envelope(40102, null, 'token expired') : envelope(0, { ok: true }),
        status: expired ? 401 : 200,
        statusText: '',
        headers: {},
        config,
      } as AxiosResponse
    }

    const [a, b] = await Promise.all([apiGet<{ ok: boolean }>('/works'), apiGet('/credits/balance')])
    expect(a).toEqual({ ok: true })
    expect(b).toEqual({ ok: true })
    expect(refreshCalls).toBe(1)
  })

  it('刷新失败（无有效会话 Cookie）时踢登录（不 toast）', async () => {
    const { store } = stubBrowser()
    store.set('meloyu:token', 'old-access')

    let refreshCalls = 0
    http.defaults.adapter = (config) => {
      if ((config.url ?? '').includes('/auth/refresh')) {
        refreshCalls += 1
        return Promise.resolve({
          data: envelope(40101, null, 'refresh token invalid'),
          status: 401,
          statusText: '',
          headers: {},
          config,
        } as AxiosResponse)
      }
      return Promise.resolve({
        data: envelope(40102, null, 'token expired'),
        status: 401,
        statusText: '',
        headers: {},
        config,
      } as AxiosResponse)
    }

    const err = await apiGet('/works').catch((e: unknown) => e)
    expect((err as ApiError).code).toBe(40102)
    expect(refreshCalls).toBe(1) // 尝试过一次 Cookie 刷新
    expect(store.get('meloyu:token')).toBeUndefined()
    expect(currentHash()).toBe('#/login')
    expect(useToastStore.getState().toasts.length).toBe(0)
  })

  it('refresh 也失效（网络/HTTP 错误）时清 token 踢登录，不递归刷新', async () => {
    const { store } = stubBrowser()
    store.set('meloyu:token', 'old-access')

    let refreshCalls = 0
    http.defaults.adapter = (config) => {
      const url = config.url ?? ''
      if (url.includes('/auth/refresh')) {
        refreshCalls += 1
        return Promise.reject(
          new AxiosError('unauthorized', AxiosError.ERR_BAD_REQUEST, config, undefined, {
            data: envelope(40101, null, 'refresh token expired'),
            status: 401,
            statusText: '',
            headers: {},
            config,
          } as AxiosResponse),
        )
      }
      return Promise.resolve({
        data: envelope(40102, null, 'token expired'),
        status: 401,
        statusText: '',
        headers: {},
        config,
      } as AxiosResponse)
    }

    const err = await apiGet('/works').catch((e: unknown) => e)
    expect((err as ApiError).code).toBe(40102) // 原请求错误向外抛
    expect(refreshCalls).toBe(1) // 只试了一次刷新，无递归
    expect(store.get('meloyu:token')).toBeUndefined()
    expect(currentHash()).toBe('#/login')
  })

  it('40101（未认证）不做刷新，直接踢登录', async () => {
    const { store } = stubBrowser()
    store.set('meloyu:token', 'access')

    let refreshCalls = 0
    http.defaults.adapter = (config) => {
      if ((config.url ?? '').includes('/auth/refresh')) {
        refreshCalls += 1
      }
      return Promise.resolve({
        data: envelope(40101, null, 'not authenticated'),
        status: 401,
        statusText: '',
        headers: {},
        config,
      } as AxiosResponse)
    }

    const err = await apiGet('/works').catch((e: unknown) => e)
    expect((err as ApiError).code).toBe(40101)
    expect(refreshCalls).toBe(0)
    expect(currentHash()).toBe('#/login')
  })
})
