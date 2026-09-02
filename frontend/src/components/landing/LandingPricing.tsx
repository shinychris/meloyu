import { useNavigate } from 'react-router-dom'
import { PLANS } from '../../lib/landing-data'
import { useT } from '../../i18n'

/** 定价四档（静态展示版：与工作台「定价与积分」同源，登录后可切换档位） */
export default function LandingPricing() {
  const navigate = useNavigate()
  const t = useT()
  return (
    <section id="pricing" className="scroll-mt-20">
      <div className="label">{t('landing.pricing.label')}</div>
      <h2 className="text-[26px] font-extrabold tracking-tight mt-2">{t('landing.pricing.title')}</h2>
      <p className="text-[13px] mt-2 max-w-[560px]" style={{ color: 'var(--muted)' }}>
        {t('landing.pricing.desc')}
      </p>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-px mt-8" style={{ background: 'var(--line)' }}>
        {PLANS.map((p) => (
          <div
            key={p.code}
            className="p-6 relative flex flex-col"
            style={{
              background: p.popular ? 'var(--bg2)' : 'var(--bg)',
              boxShadow: p.popular ? 'inset 0 2px 0 var(--acc)' : undefined,
            }}
          >
            {p.popular && (
              <div className="absolute top-0 right-0 text-[9px] font-bold px-2 py-1" style={{ background: 'var(--acc)', color: '#000' }}>
                {t('landing.pricing.popular')}
              </div>
            )}
            <div className="label" style={p.popular ? { color: 'var(--acc)' } : undefined}>
              {t(p.name)}
            </div>
            <div className="price-num !text-[36px] mt-4">
              {p.monthly == null ? t('landing.pricing.custom') : `¥${p.yearly}`}
              {p.monthly != null && (
                <span className="text-[13px] font-bold" style={{ color: 'var(--muted)' }}>
                  {' '}
                  {t('landing.pricing.perMonth')}
                </span>
              )}
            </div>
            <div className="text-[11px] mt-1.5" style={{ color: 'var(--dim)' }}>
              {p.monthly != null && p.monthly > 0 ? t('landing.pricing.monthly', { p: p.monthly }) : ''}
              {t(p.tagline)}
            </div>
            <ul className="mt-5 space-y-2 flex-1">
              {p.features.map((f) => (
                <li key={f} className="text-[12px] leading-relaxed flex gap-2" style={{ color: 'var(--muted)' }}>
                  <span style={{ color: p.popular ? 'var(--acc)' : 'var(--dim)' }}>·</span>
                  {t(f)}
                </li>
              ))}
            </ul>
            <button
              className={`btn w-full mt-6 ${p.popular ? 'btn-acc' : 'btn-ghost'}`}
              onClick={() => navigate('/login')}
            >
              {p.code === 'team'
                ? t('landing.pricing.cta.contact')
                : p.code === 'free'
                  ? t('landing.pricing.cta.free')
                  : t('landing.pricing.cta.select', { name: t(p.name) })}
            </button>
          </div>
        ))}
      </div>
      <p className="text-[11px] mt-4" style={{ color: 'var(--dim)' }}>
        {t('landing.pricing.footnote')}
      </p>
    </section>
  )
}
