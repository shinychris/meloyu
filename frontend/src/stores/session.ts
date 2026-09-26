import { create } from 'zustand'
import type { AuthData, User } from '../types/api'
import { clearToken, setToken } from '../lib/token'
import { fetchMe } from '../api/auth'
import { ApiError } from '../api/client'
import { getCreditsBalance } from '../api/account'
import { useStudioStore } from './studio'
import { usePlayerStore } from './player'

function isAuthReject(e: unknown): boolean {
  return e instanceof ApiError && (e.code === 40101 || e.code === 40102)
}

interface SessionState {
  user: User | null
  ready: boolean
  /** 后端不可达（网络故障）：token 仍在，不踢登录，展示重试（P1-25） */
  offline: boolean
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
  offline: false,

  setAuthenticated(data) {
    setToken(data.access_token)
    // v0.13.0：refresh token 由后端 Set-Cookie（HttpOnly）下发，前端不再经手；
    // 40102 时 client.ts 凭 Cookie 静默刷新
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
          offline: false,
        })
        return
      } catch (e) {
        // P1-25：只有真正的鉴权失效才踢登录；网络抖动/后端暂不可达时保留
        // token 进入 offline 重试态——否则付费用户 30 秒断网刷新就被要求重输密码
        if (isAuthReject(e)) {
          clearToken()
          set({ user: null, ready: true, offline: false })
        } else {
          set({ ready: true, offline: true })
        }
        return
      }
    }
    set({ ready: true })
  },
}))
