import { create } from 'zustand'
import type { AuthData, User } from '../types/api'
import { clearToken, setToken, setRefreshToken } from '../lib/token'
import { fetchMe } from '../api/auth'
import { getCreditsBalance } from '../api/account'
import { useStudioStore } from './studio'
import { usePlayerStore } from './player'

interface SessionState {
  user: User | null
  ready: boolean
  /** 登录/注册成功：存 token + 用户 */
  setAuthenticated: (data: AuthData) => void
  /** 登出：清 token、停轮询、停播放器 */
  logout: () => void
  /** 重新拉取 /auth/me（生成成功/切档后刷新积分） */
  refreshUser: () => Promise<void>
  /** 只刷新积分余额（提交生成即时扣分后同步侧栏，不等任务终态） */
  refreshCredits: () => Promise<void>
  /** 契约 §13.5：登录后首屏并行 /auth/me + /credits/balance */
  bootstrap: () => Promise<void>
}

export const useSessionStore = create<SessionState>((set, get) => ({
  user: null,
  ready: false,

  setAuthenticated(data) {
    setToken(data.access_token)
    // v0.7.0：轮换式 refresh token 与 access 同存 localStorage，40102 时静默刷新
    if (data.refresh_token) setRefreshToken(data.refresh_token)
    set({ user: data, ready: true })
  },

  logout() {
    clearToken()
    useStudioStore.getState().stopPolling()
    useStudioStore.getState().resetForNewWork()
    usePlayerStore.getState().stop()
    set({ user: null, ready: true })
  },

  async refreshUser() {
    try {
      const user = await fetchMe()
      set({ user })
    } catch {
      /* 拦截器已 toast / 跳登录 */
    }
  },

  async refreshCredits() {
    try {
      const balance = await getCreditsBalance()
      const user = get().user
      if (user) {
        set({ user: { ...user, credits: { ...user.credits, balance: balance.balance } } })
      }
    } catch {
      /* 静默：余额刷新失败不打断创作流 */
    }
  },

  async bootstrap() {
    if (!get().user) {
      try {
        const [user, balance] = await Promise.all([fetchMe(), getCreditsBalance()])
        // 侧边栏积分数以 /auth/me 的 credits.balance 为准（契约 §13.5）
        set({
          user: { ...user, credits: { ...user.credits, balance: balance.balance } },
          ready: true,
        })
        return
      } catch {
        set({ user: null, ready: true })
        return
      }
    }
    set({ ready: true })
  },
}))
