import { useI18nStore, LOCALES, LOCALE_LABEL } from '../../i18n'

/**
 * 语言切换（EN | 中文）。Sidebar 底部与 Landing 导航共用；
 * 亮暗两套环境都走现有设计变量（--line/--dim/--acc）。
 */
export default function LangSwitch() {
  const locale = useI18nStore((s) => s.locale)
  const setLocale = useI18nStore((s) => s.setLocale)

  return (
    <div
      className="inline-flex items-center rounded-full overflow-hidden"
      style={{ border: '1px solid var(--line)' }}
      role="group"
      aria-label="Language"
    >
      {LOCALES.map((l) => (
        <button
          key={l}
          className={`px-2 py-[2px] text-[10px] font-bold leading-none transition-colors ${
            l === locale ? '' : 'opacity-70 hover:opacity-100'
          }`}
          style={{
            background: l === locale ? 'var(--acc)' : 'transparent',
            color: l === locale ? '#000' : 'var(--dim)',
          }}
          onClick={() => setLocale(l)}
          aria-pressed={l === locale}
        >
          {LOCALE_LABEL[l]}
        </button>
      ))}
    </div>
  )
}
