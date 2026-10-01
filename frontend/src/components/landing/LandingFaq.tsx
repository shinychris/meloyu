import { FAQS } from '../../lib/landing-data'
import { useT } from '../../i18n'
import { EqMark } from './EqMark'

/** FAQ：原生 details 折叠（无 JS 状态，键盘可访问） */
export default function LandingFaq() {
  const t = useT()
  return (
    <section id="faq" className="scroll-mt-20">
      <div className="label flex items-center gap-2"><EqMark />{t('landing.faq.label')}</div>
      <h2 className="text-2xl font-extrabold tracking-tight mt-2">{t('landing.faq.title')}</h2>
      <div className="mt-8 space-y-3 max-w-[820px]">
        {FAQS.map((f) => (
          <details key={f.q} className="faq card">
            <summary className="flex items-center justify-between px-5 py-4 select-none">
              <span className="text-base font-bold">{t(f.q)}</span>
              <span className="faq-plus text-lg font-bold leading-none text-acc">
                +
              </span>
            </summary>
            <p className="px-5 pb-5 -mt-1 text-sm leading-relaxed text-muted">
              {t(f.a)}
            </p>
          </details>
        ))}
      </div>
    </section>
  )
}
