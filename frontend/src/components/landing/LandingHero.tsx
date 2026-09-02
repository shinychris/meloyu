import { useNavigate } from 'react-router-dom'
import { INSPIRE_CHIPS, LANDING_METRICS } from '../../lib/landing-data'
import { useT } from '../../i18n'
import { scrollToSection } from './LandingNav'

/** Hero：定位语 + 双 CTA + 灵感 chips + 指标条 */
export default function LandingHero() {
  const navigate = useNavigate()
  const t = useT()
  return (
    <section className="landing-hero-bg relative overflow-hidden">
      <div className="landing-grid absolute inset-0 pointer-events-none" />
      <div className="relative max-w-[1080px] mx-auto px-6 pt-20 pb-0 text-center">
        <div className="label !text-[10px]" style={{ color: 'var(--acc)' }}>
          {t('landing.hero.eyebrow')}
        </div>
        <h1 className="text-[40px] md:text-[56px] font-extrabold tracking-tight leading-[1.08] mt-5">
          {t('landing.hero.title.a')}
          <br />
          {t('landing.hero.title.b1')}
          <span style={{ color: 'var(--acc)' }}>{t('landing.hero.title.b2')}</span>
          {t('landing.hero.title.b3')}
        </h1>
        <p className="text-[14px] md:text-[15px] mt-6 max-w-[640px] mx-auto leading-relaxed" style={{ color: 'var(--muted)' }}>
          {t('landing.hero.desc.1')}
          <br />
          {t('landing.hero.desc.2')}
        </p>
        <div className="flex items-center justify-center gap-4 mt-9 flex-wrap">
          <button className="btn btn-acc !px-7 !py-3 !text-[13px]" onClick={() => navigate('/login')}>
            {t('landing.hero.cta.primary')}
          </button>
          <button className="btn btn-ghost !px-7 !py-3 !text-[13px]" onClick={() => scrollToSection('pricing')}>
            {t('landing.hero.cta.secondary')}
          </button>
        </div>
        <div className="flex items-center justify-center gap-2 mt-8 flex-wrap max-w-[720px] mx-auto">
          {INSPIRE_CHIPS.slice(0, 10).map((c, i) => (
            <button
              key={c}
              className={`chip ${i === 2 ? 'acc-on' : ''} !text-[11px]`}
              title={t('landing.hero.chipHint')}
              onClick={() => navigate('/login')}
            >
              {t(c)}
            </button>
          ))}
        </div>
      </div>
      <div className="relative max-w-[1080px] mx-auto px-6 mt-14">
        <div className="grid grid-cols-2 md:grid-cols-5 border-y" style={{ borderColor: 'var(--line)' }}>
          {LANDING_METRICS.map((m) => (
            <div key={m.label} className="py-6 text-center border-r last:border-r-0 md:border-r" style={{ borderColor: 'var(--line)' }}>
              <div className="text-[30px] font-extrabold num tracking-tight" style={{ color: 'var(--acc)' }}>
                {m.value}
              </div>
              <div className="label mt-1.5">{t(m.label)}</div>
            </div>
          ))}
        </div>
      </div>
      {/* Hero 主视觉：工作台真机截图 */}
      <div className="relative max-w-[1080px] mx-auto px-6 pt-10 pb-16">
        <div
          className="border"
          style={{ borderColor: 'var(--line2)', boxShadow: '0 0 60px rgba(0,255,44,.06), 0 24px 48px rgba(0,0,0,.5)' }}
        >
          <div className="flex items-center gap-1.5 px-3 py-2 border-b" style={{ borderColor: 'var(--line)', background: 'var(--bg2)' }}>
            <span className="dot" style={{ background: 'var(--bad)' }} />
            <span className="dot" style={{ background: 'var(--warn)' }} />
            <span className="dot" style={{ background: 'var(--acc)' }} />
            <span className="label ml-2">{t('landing.hero.shotLabel')}</span>
          </div>
          <img src="/shots/studio.png" alt={t('landing.hero.shotAlt')} className="w-full block" />
        </div>
      </div>
    </section>
  )
}
