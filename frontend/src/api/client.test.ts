import { afterEach, describe, expect, it } from 'vitest'
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

afterEach(() => {
  useToastStore.setState({ toasts: [] })
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
