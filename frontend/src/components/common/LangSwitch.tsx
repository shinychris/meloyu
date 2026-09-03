import { useEffect, useRef, useState } from 'react'
import { useI18nStore, useT, getLocale, LOCALES, LOCALE_LABEL, type Locale, type TranslationKey } from '../../i18n'

const LANG_NAME: Record<Locale, TranslationKey> = {
  en: 'common.lang.en',
  zh: 'common.lang.zh',
}

/**
 * 语言切换下拉（v0.7.2：按钮组改下拉菜单）。Sidebar 底部与 Landing 导航共用；
 * 触发器用语言代码（EN/ZH，两语言下均零违规），菜单项按当前界面语言渲染全名。
 * up=true 向上展开（侧栏底部场景，避开下方固定播放器）；默认向下。
 * 交互与视觉跟随 AccountMenu：外点/Escape 关闭 + langmenu 令牌。
 */
export default function LangSwitch({ up = false }: { up?: boolean }) {
  const t = useT() // 订阅 locale 变化驱动重渲染（取值时序与 t() 一致，SSR 冒烟友好）
  const setLocale = useI18nStore((s) => s.setLocale)
  const locale = getLocale()
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="relative" ref={wrapRef}>
      <button
        className="inline-flex items-center gap-1.5 rounded-full overflow-hidden px-2.5 py-[3px] text-[10px] font-bold leading-none transition-colors"
        style={{
          border: '1px solid var(--line)',
          color: open ? 'var(--acc)' : 'var(--dim)',
        }}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('common.language')}
        title={t('common.language')}
        onClick={() => setOpen((v) => !v)}
      >
        {/* 地球图标（语言选择的通用符号） */}
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.4" />
          <ellipse cx="8" cy="8" rx="2.8" ry="6.5" stroke="currentColor" strokeWidth="1.2" />
          <path d="M1.7 8h12.6M2.6 4.6h10.8M2.6 11.4h10.8" stroke="currentColor" strokeWidth="1.1" />
        </svg>
        <span>{LOCALE_LABEL[locale]}</span>
        <span aria-hidden="true" style={{ fontSize: 8, transform: open ? 'rotate(180deg)' : undefined }}>▾</span>
      </button>

      {open && (
        <ul className={`langmenu${up ? ' up' : ''}`} role="listbox" aria-label={t('common.language')}>
          {LOCALES.map((l) => (
            <li key={l} role="option" aria-selected={l === locale}>
              <button
                type="button"
                className={`langmenu-item${l === locale ? ' on' : ''}`}
                onClick={() => {
                  setLocale(l)
                  setOpen(false)
                }}
              >
                <span>{t(LANG_NAME[l])}</span>
                {l === locale && <span aria-hidden="true">✓</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
