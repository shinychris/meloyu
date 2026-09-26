import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { hasOnboardChoice, markOnboardChoice, useUiStore } from '../../stores/ui'
import { t, useI18nStore } from '../../i18n'

/** node 环境无 localStorage：内存桩覆盖按用户记录/旧标记兼容/容错分支 */
function makeStorage(): Storage {
  const m = new Map<string, string>()
  return {
    getItem: (k) => m.get(k) ?? null,
    setItem: (k, v) => void m.set(k, String(v)),
    removeItem: (k) => void m.delete(k),
    clear: () => m.clear(),
    key: (i) => [...m.keys()][i] ?? null,
    get length() {
      return m.size
    },
  } as Storage
}

beforeEach(() => {
  vi.stubGlobal('localStorage', makeStorage())
  useUiStore.setState({ askOpen: false, onboardingOpen: false, onboardingStep: 0 })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

/** 询问弹窗文案：en/zh 词条齐全（缺 key 时 t() 会回显 key 本身，断言兜住拼写错误） */
describe('OnboardingAsk i18n keys', () => {
  it('en 词条存在', () => {
    expect(t('layout.ob.askTitle')).toBe('Take the 4-step tour?')
    expect(t('layout.ob.askDesc')).toContain('reopen the tour anytime')
    expect(t('layout.ob.askStart')).toBe('Start tour')
    expect(t('layout.ob.askSkip')).toBe('Not now')
  })

  it('zh 词条存在', () => {
    useI18nStore.getState().setLocale('zh')
    expect(t('layout.ob.askTitle')).toBe('是否开启新手引导？')
    expect(t('layout.ob.askDesc')).toContain('随时可在侧栏左下角重新打开')
    expect(t('layout.ob.askStart')).toBe('开启引导')
    expect(t('layout.ob.askSkip')).toBe('暂不')
  })
})

/** 询问结果按用户维度记录：选择一次后同用户不再询问，其他用户首次仍询问 */
describe('onboard choice persistence', () => {
  it('未记录时视为未选择；记录后同用户已选择、其他用户仍询问', () => {
    expect(hasOnboardChoice('u1')).toBe(false)
    expect(hasOnboardChoice('u2')).toBe(false)
    markOnboardChoice('u1')
    expect(hasOnboardChoice('u1')).toBe(true)
    expect(hasOnboardChoice('u2')).toBe(false)
  })

  it('旧版设备级标记（≤v0.13.0 完成过引导）置位后所有用户不再询问', () => {
    localStorage.setItem('meloyu:onboarded:v1', '1')
    expect(hasOnboardChoice('u1')).toBe(true)
    expect(hasOnboardChoice('u2')).toBe(true)
  })

  it('localStorage 不可用时容错为未选择（不抛错）', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('denied')
      },
    })
    expect(hasOnboardChoice('u1')).toBe(false)
    expect(() => markOnboardChoice('u1')).not.toThrow()
  })
})

/** 询问弹窗 → 引导的 store 流转 */
describe('ui store ask/tour transitions', () => {
  it('resolveAsk(true) 关询问并从第一步开启引导；resolveAsk(false) 仅关询问', () => {
    useUiStore.setState({ askOpen: true, onboardingStep: 3 })
    useUiStore.getState().resolveAsk(true)
    expect(useUiStore.getState().askOpen).toBe(false)
    expect(useUiStore.getState().onboardingOpen).toBe(true)
    expect(useUiStore.getState().onboardingStep).toBe(0)

    useUiStore.setState({ askOpen: true, onboardingOpen: false })
    useUiStore.getState().resolveAsk(false)
    expect(useUiStore.getState().askOpen).toBe(false)
    expect(useUiStore.getState().onboardingOpen).toBe(false)
  })

  it('手动开启引导（侧栏按钮）同时收起询问弹窗', () => {
    useUiStore.setState({ askOpen: true })
    useUiStore.getState().startOnboarding()
    expect(useUiStore.getState().askOpen).toBe(false)
    expect(useUiStore.getState().onboardingOpen).toBe(true)
  })
})
