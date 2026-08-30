/**
 * axios 统一封装（架构文档 §11 / 契约 §1）：
 * - baseURL /api/v1（Vite 代理 → 127.0.0.1:8000）
 * - 请求自动注入 Authorization: Bearer <token>
 * - 成功解包 {code,message,data} → 直接返回 data
 * - code!==0 / HTTP 4xx/5xx → 抛 ApiError 并统一 toast（401 静默跳登录）
 * - responseType=blob 的请求（文件流/证书）不解包
 */
import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import { getToken, clearToken } from '../lib/token'
import { useToastStore } from '../stores/toast'

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

interface EnvelopeLike {
  code?: number
  message?: string
}

instance.interceptors.response.use(
  (res) => {
    // 文件流（blob）不解包
    if (res.config.responseType === 'blob') return res
    const body = res.data as EnvelopeLike
    if (body && typeof body === 'object' && typeof body.code === 'number') {
      if (body.code !== 0) {
        const err = new ApiError(body.code, body.message ?? '请求失败', res.config.url ?? '')
        if (isAuthExpired(err.code)) {
          redirectToLogin()
        } else {
          useToastStore.getState().push(err.message)
        }
        throw err
      }
      return res.data?.data
    }
    return res.data
  },
  (error: AxiosError) => {
    const status = error.response?.status
    let code = 50001
    let message = '服务暂不可用，请稍后重试'
    const body = error.response?.data as EnvelopeLike | undefined
    if (body && typeof body === 'object' && typeof body.code === 'number') {
      code = body.code
      message = body.message ?? message
    } else if (status != null) {
      message = status >= 500 ? '服务内部错误，请稍后重试' : `请求失败（HTTP ${status}）`
    } else if (error.code === 'ECONNABORTED') {
      message = '请求超时，请检查网络'
    }
    const err = new ApiError(code, message, error.config?.url ?? '')
    if (isAuthExpired(code)) {
      redirectToLogin()
    } else {
      useToastStore.getState().push(message)
    }
    throw err
  },
)

/** JSON GET：返回已解包的 data */
export async function apiGet<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const data = await instance.get(url, { params })
  return data as T
}

/** JSON POST */
export async function apiPost<T>(url: string, body?: unknown): Promise<T> {
  const data = await instance.post(url, body ?? {})
  return data as T
}

/** JSON PATCH */
export async function apiPatch<T>(url: string, body?: unknown): Promise<T> {
  const data = await instance.patch(url, body ?? {})
  return data as T
}

/** JSON DELETE */
export async function apiDelete<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const data = await instance.delete(url, { params })
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
