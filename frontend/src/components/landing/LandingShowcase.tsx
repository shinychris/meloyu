import { SHOWCASE } from '../../lib/landing-data'
import { useT, getLocale } from '../../i18n'

/** 界面一览：真机截图（按当前 locale 从 /shots/{en|zh}/ 取对应语言界面的截图） */
export default function LandingShowcase() {
  const t = useT() // 订阅 locale 变化驱动重渲染；取值走 live getLocale（SSR 冒烟一致）
  const prefix = `/shots/${getLocale()}/`
  return (
    <section id="showcase" className="scroll-mt-20">
      <div className="label">{t('landing.showcase.label')}</div>
      <h2 className="text-[26px] font-extrabold tracking-tight mt-2">{t('landing.showcase.title')}</h2>
      <p className="text-[13px] mt-2 max-w-[560px]" style={{ color: 'var(--muted)' }}>
        {t('landing.showcase.desc')}
      </p>
      <div className="grid md:grid-cols-2 gap-6 mt-8">
        {SHOWCASE.map((s) => (
          <figure key={s.src} className="card overflow-hidden hover:border-[var(--line2)] transition-colors">
            <img src={prefix + s.src} alt={`${t(s.title)} — ${t(s.desc)}`} className="w-full block border-b" style={{ borderColor: 'var(--line)' }} />
            <figcaption className="p-5">
              <div className="text-[14px] font-bold">{t(s.title)}</div>
              <p className="text-[12px] mt-1.5 leading-relaxed" style={{ color: 'var(--muted)' }}>
                {t(s.desc)}
              </p>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  )
}
