/**
 * 轻量 i18n（零新增依赖）：en / zh 双语，默认英语。
 *
 * - key 为扁平点号字符串（如 'studio.generate'），类型由 en 字典推导（TranslationKey），
 *   zh 字典受 Record<TranslationKey, string> 约束 —— 缺 key 会在 typecheck 阶段报错。
 * - 组件内用 useT()（订阅语言变化自动重渲染）；组件外 / store / api 层直接调 t()。
 * - 语言持久化 localStorage('meloyu:locale:v1')，默认 'en'；切换时同步 <html lang>。
 * - 本模块在被任何组件 import 时即完成 locale 初始化（模块副作用），无时序问题。
 */
import { create } from 'zustand'
import { en } from './en'
import { zh } from './zh'

export type Locale = 'en' | 'zh'

/** 语言切换按钮上的短标签 */
export const LOCALE_LABEL: Record<Locale, string> = { en: 'EN', zh: '中文' }
export const LOCALES: readonly Locale[] = ['en', 'zh']

export type TranslationKey = keyof typeof en

const STORAGE_KEY = 'meloyu:locale:v1'

function readStoredLocale(): Locale {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'zh' ? 'zh' : 'en'
  } catch {
    return 'en'
  }
}

function applyDocumentLocale(l: Locale): void {
  // node/测试环境（vitest 默认无 DOM）下跳过
  if (typeof document === 'undefined') return
  document.documentElement.lang = l === 'zh' ? 'zh-CN' : 'en'
}

interface I18nState {
  locale: Locale
  setLocale: (l: Locale) => void
}

export const useI18nStore = create<I18nState>((set) => ({
  locale: readStoredLocale(),
  setLocale(l) {
    try {
      localStorage.setItem(STORAGE_KEY, l)
    } catch {
      /* ignore */
    }
    set({ locale: l })
    applyDocumentLocale(l)
  },
}))

// 模块加载即纠正 <html lang>（index.html 静态默认 en；存了 zh 的用户尽早切回）
applyDocumentLocale(useI18nStore.getState().locale)

/** 当前语言（非响应式；组件内请用 useT） */
export function getLocale(): Locale {
  return useI18nStore.getState().locale
}

/** 翻译函数：`t('common.confirm')`；插值 `t('x.y', { n: 3 })` 对应字典中的 `{n}` 占位符 */
export function t(key: TranslationKey, params?: Record<string, string | number>): string {
  const raw = dicts[getLocale()][key] ?? dicts.en[key] ?? key
  if (!params) return raw
  return raw.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m))
}

/** 组件内翻译 hook：语言切换时使用它的组件自动重渲染 */
export function useT() {
  useI18nStore((s) => s.locale) // 订阅
  return t
}

const dicts: Record<Locale, Partial<Record<TranslationKey, string>>> = { en, zh }
