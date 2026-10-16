import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from './session'

/**
 * F3 修复（v0.16.2）回归：桌面冷启动不得依赖登录后才拉到的 license.mode。
 * 覆盖 session.detectDesktopShell 两条判定路径：
 * - 裸浏览器直连桌面后端：公开端点 /system/meta 下发 app_mode=desktop →
 *   置位 desktopShell 并立即 bootstrap（无 token 也能取回本地档案会话）；
 * - 云形态：app_mode=cloud → 维持登录流（desktopShell=false，不 bootstrap）。
 */
vi.mock('../api/auth', () => ({
  fetchMe: vi.fn(async () => ({ id: 1, email: 'local@meloyu.desktop', plan: 'studio' })),
}))
vi.mock('../api/account', () => ({
  getCreditsBalance: vi.fn(async () => ({ balance: 0 })),
  getSystemMeta: vi.fn(async () => ({ app_mode: 'desktop' })),
}))
vi.mock('../api/license', () => ({
  getLicenseStatus: vi.fn(async () => ({ mode: 'desktop', billing_mode: 'license', activated: false })),
}))
vi.mock('./studio', () => ({ useStudioStore: { getState: () => ({}) } }))
vi.mock('./player', () => ({ usePlayerStore: { getState: () => ({}) } }))

function resetStore() {
  useSessionStore.setState({
    user: null,
    license: null,
    ready: false,
    offline: false,
    desktopShell: false,
    shellProbed: false,
  })
}

beforeEach(() => {
  resetStore()
  vi.clearAllMocks()
})

describe('session.detectDesktopShell（F3 桌面冷启动）', () => {
  it('system/meta 判定为 desktop 后无 token 也 bootstrap 本地档案', async () => {
    expect(useSessionStore.getState().desktopShell).toBe(false)
    await useSessionStore.getState().detectDesktopShell()
    const s = useSessionStore.getState()
    expect(s.desktopShell).toBe(true)
    expect(s.user?.email).toBe('local@meloyu.desktop')
    expect(s.ready).toBe(true)
    expect(s.license?.mode).toBe('desktop')
  })

  it('cloud 形态不置位、不拉会话（走既有登录流）', async () => {
    const { getSystemMeta } = await import('../api/account')
    vi.mocked(getSystemMeta).mockResolvedValueOnce({ app_mode: 'cloud' } as never)
    await useSessionStore.getState().detectDesktopShell()
    const s = useSessionStore.getState()
    expect(s.desktopShell).toBe(false)
    expect(s.user).toBeNull()
    // 探测只跑一次：后续调用直接返回（StrictMode 双效应防抖）
    await useSessionStore.getState().detectDesktopShell()
    expect(getSystemMeta).toHaveBeenCalledTimes(1)
  })
})
