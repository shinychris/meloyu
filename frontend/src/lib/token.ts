/** JWT 本地存取（localStorage）。v0.7.0 起为 token 对：
 *  access（86400s）+ 轮换式 refresh，40102 时由 client.ts 静默刷新重放。 */
const TOKEN_KEY = 'meloyu:token'
const REFRESH_KEY = 'meloyu:refresh-token'

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

export function getRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY)
  } catch {
    return null
  }
}

export function setRefreshToken(token: string): void {
  try {
    localStorage.setItem(REFRESH_KEY, token)
  } catch {
    /* 隐私模式下忽略 */
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
  } catch {
    /* ignore */
  }
}
