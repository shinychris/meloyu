import { create } from 'zustand'
import type { AuthData, LicenseStatus, User } from '../types/api'
import { clearToken, setToken } from '../lib/token'
import { fetchMe } from '../api/auth'
import { ApiError } from '../api/client'
import { getCreditsBalance, getSystemMeta } from '../api/account'
import { getLicenseStatus } from '../api/license'
import { useStudioStore } from './studio'
import { usePlayerStore } from './player'

function isAuthReject(e: unknown): boolean {
  return e instanceof ApiError && (e.code === 40101 || e.code === 40102)
}

/** 桌面壳内运行（Electron preload 桥）；模块加载即同步判定，避免首帧闪登录页 */
const inDesktopShell =
  typeof window !== 'undefined' && Boolean(window.meloyuDesktop)

interface SessionState {
  user: User | null
  /** v0.16.0 买断制：试用/激活状态（bootstrap 时并行拉取；cloud 模式 mode=cloud） */
  license: LicenseStatus | null
  ready: boolean
  /** 后端不可达（网络故障）：token 仍在，不踢登录，展示重试 */
  offline: boolean
  /**
   * 桌面形态判定（F3 修复，2026-10-16）：壳桥或桌面后端 app_mode 命中即为 true。
   * 判定后无 token 也执行 bootstrap——桌面免登录短路在 sidecar 生效，
   * 冷启动不再被 hasToken 门控卡在登录页（原死锁：bootstrap 只在 AppLayout 内调用，
   * 而 AppLayout 被 hasToken 门控，随机端口下 localStorage 无跨启动 token）。
   */
  desktopShell: boolean
  /** 形态探测只跑一次（StrictMode 双效应/路由重挂载防抖） */
  shellProbed: boolean
  /** 登录/注册成功：存 token + 用户 */
  setAuthenticated: (data: AuthData) => void
  /** 登出：清 token、停轮询、停播放器 */
  logout: () => void
  /**  离线重试：回到「会话未就绪」态并重新 bootstrap（App.tsx 改调本 action） */
  retryBootstrap: () => void
  /** 登录页守卫用：本地无 token 时清空残留会话（401 后避免回跳循环） */
  clearStaleSession: () => void
  /** 重新拉取 /auth/me（生成成功/切档后刷新积分） */
  refreshUser: () => Promise<void>
  /** 只刷新积分余额（提交生成即时扣分后同步侧栏，不等任务终态） */
  refreshCredits: () => Promise<void>
  /** 激活/解除后刷新授权状态（v0.16.0：侧栏徽标与激活页数据源） */
  refreshLicense: () => Promise<void>
  /** 应用形态探测：桌面后端（裸浏览器直连）兜底判定 + 桌面态立即拉本地档案会话 */
  detectDesktopShell: () => Promise<void>
  /** ：登录后首屏并行 /auth/me + /credits/balance */
  bootstrap: () => Promise<void>
}

export const useSessionStore = create<SessionState>((set, get) => ({
  user: null,
  license: null,
  ready: false,
  offline: false,
  desktopShell: inDesktopShell,
  shellProbed: inDesktopShell,

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

  retryBootstrap() {
    set({ ready: false, offline: false })
    void get().bootstrap()
  },

  clearStaleSession() {
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

  /** 激活/解除后刷新授权状态（侧栏徽标与激活页数据源） */
  async refreshLicense() {
    try {
      set({ license: await getLicenseStatus() })
    } catch {
      /* 静默：授权状态不可达不打断创作流 */
    }
  },

  /**
   * 应用形态探测（F3）：壳桥在模块加载时已同步判定；此处为裸浏览器直连桌面
   * 后端的兜底——公开端点 /system/meta 下发 app_mode，命中 desktop 即视同桌面
   * 形态并立即 bootstrap（免登录短路取本地档案）。云形态/后端不可达走既有登录流。
   */
  async detectDesktopShell() {
    if (get().shellProbed) return
    set({ shellProbed: true })
    if (get().desktopShell) {
      await get().bootstrap()
      return
    }
    try {
      const meta = await getSystemMeta()
      if (meta.app_mode === 'desktop') {
        set({ desktopShell: true })
        await get().bootstrap()
      }
    } catch {
      /* 后端不可达：维持云形态冷启动流（offline 重试态由 AppLayout 处理） */
    }
  },

  async bootstrap() {
    if (!get().user) {
      try {
        const [user, balance, license] = await Promise.all([
          fetchMe(),
          getCreditsBalance(),
          getLicenseStatus().catch(() => null),
        ])
        // 侧边栏积分数以 /auth/me 的 credits.balance 为准；
        // license 状态拉取失败不阻塞会话（cloud 未登录语义下 401 由前两者兜底）
        set({
          user: { ...user, credits: { ...user.credits, balance: balance.balance } },
          license,
          ready: true,
          offline: false,
        })
        return
      } catch (e) {
        // ：只有真正的鉴权失效才踢登录；网络抖动/后端暂不可达时保留
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
