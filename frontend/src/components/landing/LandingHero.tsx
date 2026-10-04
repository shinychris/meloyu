import { useNavigate } from 'react-router-dom'
import { INSPIRE_CHIPS, LANDING_METRICS } from '../../lib/landing-data'
import { useT, getLocale } from '../../i18n'
import { scrollToSection } from './LandingNav'
import { useSiteMode } from './SiteMode'

/** Hero：定位语 + 双 CTA + 灵感 chips + 指标条 */
export default function LandingHero() {
  const navigate = useNavigate()
  const t = useT()
  const site = useSiteMode()
  return (
    <section className="landing-hero-bg relative overflow-hidden">
      <div className="landing-grid absolute inset-0 pointer-events-none" />
      <div className="relative max-w-[1080px] mx-auto px-6 pt-20 pb-0 text-center">
        <div className="label" style={{ color: 'var(--acc)' }}>
          {t('landing.hero.eyebrow')}
        </div>
        <h1 className="text-5xl md:text-hero font-extrabold tracking-tight leading-[1.08] mt-5">
          {t('landing.hero.title.a')}
          <br />
          {t('landing.hero.title.b1')}
          <span className="text-acc">{t('landing.hero.title.b2')}</span>
          {t('landing.hero.title.b3')}
        </h1>
        <p className="text-md mt-6 max-w-[640px] mx-auto leading-relaxed text-muted">
          {t('landing.hero.desc.1')}
          <br />
          {t('landing.hero.desc.2')}
        </p>
        <div className="flex items-center justify-center gap-4 mt-9 flex-wrap">
          <button className="btn btn-acc btn-lg" onClick={() => scrollToSection('pricing')}>
            {t('landing.hero.cta.primary')}
          </button>
          {!site && (
            <button className="btn btn-ghost btn-lg" onClick={() => navigate('/login')}>
              {t('landing.hero.cta.secondary')}
            </button>
          )}
        </div>
        <div className="flex items-center justify-center gap-2 mt-8 flex-wrap max-w-[720px] mx-auto">
          {INSPIRE_CHIPS.slice(0, 10).map((c, i) => (
            <button
              key={c}
              className={`chip ${i === 2 ? 'acc-on' : ''}`}
              title={t('landing.hero.chipHint')}
              onClick={site ? undefined : () => navigate('/login')}
            >
              {t(c)}
            </button>
          ))}
        </div>
      </div>
      <div className="relative max-w-[1080px] mx-auto px-6 mt-14">
        <div className="grid grid-cols-2 md:grid-cols-5 border-y border-line">
          {LANDING_METRICS.map((m, i) => (
            <div
              key={m.label}
              className={`py-6 text-center border-r last:border-r-0 md:border-r border-line ${i === LANDING_METRICS.length - 1 ? 'max-md:col-span-2' : ''}`}
            >
              <div className="text-4xl font-extrabold num tracking-tight text-acc">
                {m.value}
              </div>
              <div className="label mt-1.5">{t(m.label)}</div>
            </div>
          ))}
        </div>
      </div>
      {/* Hero 主视觉：工作台真机截图 */}
      <div className="relative max-w-[1080px] mx-auto px-6 pt-10 pb-16">
        <div className="border border-line-2 shadow-shot">
          <div className="flex items-center gap-1.5 px-3 py-2 border-b border-line bg-bg-2">
            <span className="dot" style={{ background: 'var(--bad)' }} />
            <span className="dot" style={{ background: 'var(--warn)' }} />
            <span className="dot" style={{ background: 'var(--acc)' }} />
            <span className="label ml-2">{t('landing.hero.shotLabel')}</span>
          </div>
          <img src={`/shots/${getLocale()}/studio.png`} alt={t('landing.hero.shotAlt')} className="w-full block" />
        </div>
      </div>
    </section>
  )
}
