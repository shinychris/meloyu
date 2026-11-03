import { AUDIENCES } from '../../lib/landing-data'
import { useT } from '../../i18n'
import { EqMark } from './EqMark'

/** 目标用户三场景 + 合规口径说明条（对齐  红线：不绝对化商用承诺） */
export default function LandingAudience() {
  const t = useT()
  return (
    <section>
      <div className="label flex items-center gap-2"><EqMark />{t('landing.audience.label')}</div>
      <h2 className="text-2xl font-extrabold tracking-tight mt-2">{t('landing.audience.title')}</h2>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-8">
        {AUDIENCES.map((a) => (
          <div key={a.title} className="card p-6 hover:border-line-2 transition-colors">
            <div className="text-lg font-extrabold">{t(a.title)}</div>
            <div className="text-xs mt-1 text-acc">{t(a.sub)}</div>
            <ul className="mt-4 space-y-2.5">
              {a.points.map((p) => (
                <li key={p} className="text-sm leading-relaxed flex gap-2 text-muted">
                  <span className="text-acc">·</span>
                  {t(p)}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {/* 合规口径说明 */}
      <div className="mt-6 border-l-2 border-acc bg-bg-2 pl-5 py-1">
        <div className="label" style={{ color: 'var(--acc)' }}>
          {t('landing.audience.complianceLabel')}
        </div>
        <p className="text-sm mt-2 leading-relaxed text-muted">
          {t('landing.audience.complianceP1')}
          <span className="text-txt">{t('landing.audience.complianceHL')}</span>
          {t('landing.audience.complianceP2')}
        </p>
      </div>
    </section>
  )
}
