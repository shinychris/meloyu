import { create } from 'zustand'

/** 跨组件 UI 态：新手引导开关 */
interface UiState {
  onboardingOpen: boolean
  onboardingStep: number
  startOnboarding: () => void
  setStep: (n: number) => void
  endOnboarding: () => void
}

export const useUiStore = create<UiState>((set) => ({
  onboardingOpen: false,
  onboardingStep: 0,
  startOnboarding() {
    set({ onboardingOpen: true, onboardingStep: 0 })
  },
  setStep(n) {
    set({ onboardingStep: n })
  },
  endOnboarding() {
    set({ onboardingOpen: false })
    try {
      localStorage.setItem('meloyu:onboarded:v1', '1')
    } catch {
      /* ignore */
    }
  },
}))

export function hasOnboarded(): boolean {
  try {
    return localStorage.getItem('meloyu:onboarded:v1') === '1'
  } catch {
    return false
  }
}
