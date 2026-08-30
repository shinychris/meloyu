import { apiGet, apiPost } from './client'
import type { AuthData, LoginRequest, RegisterRequest, User } from '../types/api'

/** POST /auth/register —— 注册（无鉴权），注册即登录 */
export function register(req: RegisterRequest): Promise<AuthData> {
  return apiPost<AuthData>('/auth/register', req)
}

/** POST /auth/login —— 登录（无鉴权） */
export function login(req: LoginRequest): Promise<AuthData> {
  return apiPost<AuthData>('/auth/login', req)
}

/** GET /auth/me —— 当前用户（鉴权） */
export function fetchMe(): Promise<User> {
  return apiGet<User>('/auth/me')
}
