/**
 * axios 统一封装（架构文档 §11 / 契约 §1）：
 * - baseURL /api/v1（Vite 代理 → 127.0.0.1:8000）
 * - 请求自动注入 Authorization: Bearer <token>
 * - 成功解包 {code,message,data} → 直接返回 data
 * - code!==0 / HTTP 4xx/5xx → 抛 ApiError 并统一 toast（401 静默处理）
 * - 40102（access 过期）：凭 HttpOnly refresh Cookie 静默刷新（单飞防并发重复
 *   刷新）并重放原请求一次；刷新失败（Cookie 无/过期）→ 清 token 跳登录
 * - 40101（未认证）→ 直接清 token 跳登录
 * - responseType=blob 的请求（文件流/证书）不解包
 */
import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'
import { getToken, setToken, clearToken } from '../lib/token'
import { useToastStore } from '../stores/toast'
import { t, getLocale } from '../i18n'

export class ApiError extends Error {
  code: number
  requestPath: string
  constructor(code: number, message: string, requestPath: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.requestPath = requestPath
  }
}

const instance = axios.create({
  baseURL: '/api/v1',
  timeout: 20000,
})

/** 导出实例仅供单测替换 adapter 使用；业务代码请用 apiGet/apiPost 等封装 */
export const http = instance

instance.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  // 后端按此 header 返回本地化的 message / 目录文案
  config.headers['Accept-Language'] = getLocale()
  return config
})

function isAuthExpired(code: number): boolean {
  return code === 40101 || code === 40102
}

function redirectToLogin(): void {
  clearToken()
  if (window.location.hash !== '#/login') {
    window.location.hash = '#/login'
  }
}

/** 40203（试用到期未激活）：跳系统设置的授权分区激活（v0.17.0 起激活迁入 /settings） */
function redirectToActivation(): void {
  if (window.location.hash !== '#/settings') {
    window.location.hash = '#/settings'
  }
}

interface EnvelopeLike {
  code?: number
  message?: string
}

/** 刷新接口的 data 形状（v0.13.0：refresh 在 HttpOnly Cookie 中，body 只有 access） */
interface RefreshData {
  access_token: string
}

/** 拦截器内部标记：已重放过一次 / 刷新请求自身（防递归刷新） */
interface RetriableConfig extends InternalAxiosRequestConfig {
  _meloyuAuthRetried?: boolean
  _meloyuSkipAuthRefresh?: boolean
}

/** 单飞刷新：并发多个 40102 共享同一次 /auth/refresh；成功落新 access。
 *  refresh 凭据在 HttpOnly Cookie 中（同源请求自动携带，v0.13.0），请求体
 *  不再传 refresh_token；失败（无会话/过期）由调用方踢登录。
 *  注意：句柄清空走 then 微任务而非 IIFE 内 finally —— 同步落定时 finally 会在
 *  外层赋值之前执行，随后赋值把已落定的 promise 装回句柄，毒化后续所有刷新
 *  （测试抓到的真实缺陷）。 */
let refreshInFlight: Promise<boolean> | null = null

async function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight
  const attempt = (async (): Promise<boolean> => {
    try {
      // 响应拦截器已解包 envelope，此处拿到的即 data（与 apiPost 同理，类型需断言）
      const res = await instance.post(
        '/auth/refresh',
        {},
        { _meloyuSkipAuthRefresh: true } as AxiosRequestConfig,
      )
      const data = res as unknown as RefreshData
      if (!data?.access_token) return false
      setToken(data.access_token)
      return true
    } catch {
      return false
    }
  })()
  refreshInFlight = attempt
  const reset = (): void => {
    if (refreshInFlight === attempt) refreshInFlight = null
  }
  void attempt.then(reset, reset)
  return attempt
}

/** 40102 统一处置：能刷新则重放原请求（一次）；否则踢登录并抛错 */
async function handleAuthExpired(
  code: number,
  config: RetriableConfig | undefined,
  makeError: () => ApiError,
): Promise<never | ReturnType<typeof instance.request>> {
  if (code === 40102 && config && !config._meloyuAuthRetried) {
    const refreshed = await refreshAccessToken()
    if (refreshed) {
      config._meloyuAuthRetried = true
      return instance.request(config)
    }
  }
  redirectToLogin()
  throw makeError()
}

instance.interceptors.response.use(
  (res) => {
    // 文件流（blob）不解包
    if (res.config.responseType === 'blob') return res
    const body = res.data as EnvelopeLike
    if (body && typeof body === 'object' && typeof body.code === 'number') {
      if (body.code !== 0) {
        const makeError = () =>
          new ApiError(body.code!, body.message ?? t('api.requestFailed'), res.config.url ?? '')
        if (isAuthExpired(body.code)) {
          // 40102 尝试静默刷新重放；40101 直接踢登录
          return handleAuthExpired(body.code, res.config as RetriableConfig, makeError)
        }
        if (body.code === 40203) {
          // 试用到期：toast 后端引导文案 + 跳激活页（生成/编辑/导出提交处触发）
          const err = makeError()
          useToastStore.getState().push(err.message)
          redirectToActivation()
          throw err
        }
        const err = makeError()
        useToastStore.getState().push(err.message)
        throw err
      }
      return res.data?.data
    }
    return res.data
  },
  (error: AxiosError) => {
    const status = error.response?.status
    let code = 50001
    let message = t('api.serverUnavailable')
    const body = error.response?.data as EnvelopeLike | undefined
    if (body && typeof body === 'object' && typeof body.code === 'number') {
      code = body.code
      message = body.message ?? message
    } else if (status != null) {
      message = status >= 500 ? t('api.internalError') : t('api.httpError', { status })
    } else if (error.code === 'ECONNABORTED') {
      message = t('api.timeout')
    }
    const makeError = () => new ApiError(code, message, error.config?.url ?? '')
    const cfg = error.config as RetriableConfig | undefined
    if (isAuthExpired(code) && !cfg?._meloyuSkipAuthRefresh) {
      return handleAuthExpired(code, cfg, makeError)
    }
    if (isAuthExpired(code)) {
      // 刷新请求自身失败（refresh token 也过期）：直接踢登录，不再递归
      redirectToLogin()
      throw makeError()
    }
    if (!cfg?._meloyuSkipAuthRefresh) {
      // 后台静默刷新的网络/服务端错误不 toast（外层统一踢登录），其余照常提示
      useToastStore.getState().push(message)
    }
    throw makeError()
  },
)

/** JSON GET：返回已解包的 data */
export async function apiGet<T>(url: string, params?: Record<string, unknown>,
  config?: AxiosRequestConfig): Promise<T> {
  const data = await instance.get(url, { params, ...config })
  return data as T
}

/** JSON POST */
export async function apiPost<T>(url: string, body?: unknown,
  config?: AxiosRequestConfig): Promise<T> {
  const data = await instance.post(url, body ?? {}, config)
  return data as T
}

/** JSON PUT */
export async function apiPut<T>(url: string, body?: unknown,
  config?: AxiosRequestConfig): Promise<T> {
  const data = await instance.put(url, body ?? {}, config)
  return data as T
}

/** JSON PATCH */
export async function apiPatch<T>(url: string, body?: unknown,
  config?: AxiosRequestConfig): Promise<T> {
  const data = await instance.patch(url, body ?? {}, config)
  return data as T
}

/** JSON DELETE */
export async function apiDelete<T>(url: string, params?: Record<string, unknown>,
  config?: AxiosRequestConfig): Promise<T> {
  const data = await instance.delete(url, { params, ...config })
  return data as T
}

/** 取 blob（证书 / 下载类接口） */
export async function apiBlob(url: string, config?: AxiosRequestConfig): Promise<Blob> {
  const res = await instance.get(url, { responseType: 'blob', ...config })
  return res.data as Blob
}

/** 触发浏览器保存文件 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}
