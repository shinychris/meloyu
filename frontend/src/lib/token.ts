/** JWT 本地存取（localStorage）。架构约定：MVP 单 token 7 天，无 refresh。 */
const TOKEN_KEY = 'meloyu:token'

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
  } catch {
    /* ignore */
  }
}
