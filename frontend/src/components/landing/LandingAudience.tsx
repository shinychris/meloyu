import { AUDIENCES } from '../../lib/landing-data'
import { useT } from '../../i18n'

/** 目标用户三场景 + 合规口径说明条（对齐 R-01 红线：不绝对化商用承诺） */
export default function LandingAudience() {
  const t = useT()
  return (
    <section>
      <div className="label">{t('landing.audience.label')}</div>
      <h2 className="text-[26px] font-extrabold tracking-tight mt-2">{t('landing.audience.title')}</h2>
      <div className="grid md:grid-cols-3 gap-4 mt-8">
        {AUDIENCES.map((a) => (
          <div key={a.title} className="card p-6 hover:border-[var(--line2)] transition-colors">
            <div className="text-[16px] font-extrabold">{t(a.title)}</div>
            <div className="text-[11px] mt-1" style={{ color: 'var(--acc)' }}>
              {t(a.sub)}
            </div>
            <ul className="mt-4 space-y-2.5">
              {a.points.map((p) => (
                <li key={p} className="text-[12px] leading-relaxed flex gap-2" style={{ color: 'var(--muted)' }}>
                  <span style={{ color: 'var(--acc)' }}>·</span>
                  {t(p)}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {/* 合规口径说明 */}
      <div className="mt-6 border-l-2 pl-5 py-1" style={{ borderColor: 'var(--acc)', background: 'var(--bg2)' }}>
        <div className="label !text-[10px]" style={{ color: 'var(--acc)' }}>
          {t('landing.audience.complianceLabel')}
        </div>
        <p className="text-[12px] mt-2 leading-relaxed" style={{ color: 'var(--muted)' }}>
          {t('landing.audience.complianceP1')}
          <span style={{ color: 'var(--txt)' }}>{t('landing.audience.complianceHL')}</span>
          {t('landing.audience.complianceP2')}
        </p>
      </div>
    </section>
  )
}
