/** JWT 本地存取（localStorage）。
 *
 * v0.13.0（安审计 M-1/M-2）：仅 access token（24h）留在 localStorage；
 * 轮换式 refresh token 改由后端经 HttpOnly+SameSite=Strict Cookie 下发
 * （Path=/api/v1/auth），JS 不可读——XSS 至多窃取短时 access，无法带走
 * 30 天刷新凭据。clearToken 顺带清理旧版本残留在 localStorage 的 refresh。 */
const TOKEN_KEY = 'meloyu:token'
const LEGACY_REFRESH_KEY = 'meloyu:refresh-token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    /* 隐私模式下忽略 */
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
    // 旧版本（≤ v0.12.3）曾把 refresh 存于此，登出时一并清除
    localStorage.removeItem(LEGACY_REFRESH_KEY)
  } catch {
    /* ignore */
  }
}
