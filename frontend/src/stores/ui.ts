import { create } from 'zustand'

/** ≤v0.13.0 的设备级「已完成引导」标记：置位过的设备视为已选择，不再弹首次询问 */
const LEGACY_FLAG = 'meloyu:onboarded:v1'
/** 首次登录询问结果按用户维度记录（开启/暂不均算已选择，之后不再询问） */
const choiceKey = (userId: string) => `meloyu:onboard-choice:v1:${userId}`

/** 跨组件 UI 态：新手引导（首次登录询问 → 四步 spotlight 引导） */
interface UiState {
  /** 首次登录询问弹窗（是否开启引导） */
  askOpen: boolean
  onboardingOpen: boolean
  onboardingStep: number
  startAsk: () => void
  /** 询问弹窗做出选择；选「开启」则直接进入引导第一步 */
  resolveAsk: (start: boolean) => void
  startOnboarding: () => void
  setStep: (n: number) => void
  endOnboarding: () => void
}

export const useUiStore = create<UiState>((set) => ({
  askOpen: false,
  onboardingOpen: false,
  onboardingStep: 0,
  startAsk() {
    set({ askOpen: true })
  },
  resolveAsk(start) {
    set({ askOpen: false })
    if (start) set({ onboardingOpen: true, onboardingStep: 0 })
  },
  startOnboarding() {
    // 手动入口（侧栏按钮）：若询问弹窗尚未弹出，视为用户已自行做出选择
    set({ onboardingOpen: true, onboardingStep: 0, askOpen: false })
  },
  setStep(n) {
    set({ onboardingStep: n })
  },
  endOnboarding() {
    set({ onboardingOpen: false })
  },
}))

/** 该用户是否已在首次登录询问中做出选择（或本设备完成过旧版引导） */
export function hasOnboardChoice(userId: string): boolean {
  try {
    return localStorage.getItem(choiceKey(userId)) !== null || localStorage.getItem(LEGACY_FLAG) === '1'
  } catch {
    return false
  }
}

/** 记录该用户的询问选择，此后登录不再询问 */
export function markOnboardChoice(userId: string): void {
  try {
    localStorage.setItem(choiceKey(userId), '1')
  } catch {
    /* ignore */
  }
}
