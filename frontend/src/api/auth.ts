import { apiBlob, apiGet, apiPost, DOWNLOAD_TIMEOUT_MS } from './client'
import type {
  AuthData,
  ChangePasswordRequest,
  DeleteAccountRequest,
  ForgotPasswordRequest,
  LoginRequest,
  OkResult,
  RegisterRequest,
  ResetPasswordRequest,
  User,
} from '../types/api'

/** POST /auth/register —— 注册（无鉴权），注册即登录 */
export function register(req: RegisterRequest): Promise<AuthData> {
  return apiPost<AuthData>('/auth/register', req)
}

/** POST /auth/send-code —— 发送注册验证码（无鉴权；60s 防刷） */
export function sendCode(email: string): Promise<OkResult> {
  return apiPost<OkResult>('/auth/send-code', { email })
}

/** POST /auth/login —— 登录（无鉴权） */
export function login(req: LoginRequest): Promise<AuthData> {
  return apiPost<AuthData>('/auth/login', req)
}

/** GET /auth/me —— 当前用户（鉴权） */
export function fetchMe(): Promise<User> {
  return apiGet<User>('/auth/me')
}

/**
 * POST /auth/refresh —— 刷新 token 对（轮换式，旧 refresh 即刻失效）。
 * 仅供 client.ts 拦截器在 40102 时静默调用（单飞）；业务代码无需直接使用。
 * （client.ts 内通过 axios 实例直调，此处不重复封装，避免循环依赖。）
 */

/** POST /auth/logout —— 登出全部设备（吊销 refresh token，需 Bearer） */
export function logoutAll(): Promise<OkResult> {
  return apiPost<OkResult>('/auth/logout')
}

/** POST /auth/forgot-password —— 忘记密码（无论账号存在与否都 ok，防枚举） */
export function forgotPassword(req: ForgotPasswordRequest): Promise<OkResult> {
  return apiPost<OkResult>('/auth/forgot-password', req)
}

/** POST /auth/reset-password —— 邮件链接 token + 新密码 */
export function resetPassword(req: ResetPasswordRequest): Promise<OkResult> {
  return apiPost<OkResult>('/auth/reset-password', req)
}

/** POST /auth/change-password —— 修改密码（需 Bearer） */
export function changePassword(req: ChangePasswordRequest): Promise<OkResult> {
  return apiPost<OkResult>('/auth/change-password', req)
}

/** POST /auth/delete-account —— 删除账号（需 Bearer；输密码确认） */
export function deleteAccount(req: DeleteAccountRequest): Promise<OkResult> {
  return apiPost<OkResult>('/auth/delete-account', req)
}

/** GET /auth/export-data —— 导出我的数据（zip 二进制流；慢网大文件放宽 300s 超时） */
export function exportData(): Promise<Blob> {
  return apiBlob('/auth/export-data', { timeout: DOWNLOAD_TIMEOUT_MS })
}
