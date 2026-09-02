import { useNavigate } from 'react-router-dom'
import { CHANNELS, LANDING_VERSION, MILESTONES } from '../../lib/landing-data'
import { useT, type TranslationKey } from '../../i18n'
import { scrollToSection } from './LandingNav'

/** 页脚锚点导航（与顶部导航共用文案 key） */
const FOOTER_LINKS: Array<{ id: string; key: TranslationKey }> = [
  { id: 'features', key: 'landing.nav.features' },
  { id: 'channels', key: 'landing.nav.channels' },
  { id: 'models', key: 'landing.nav.models' },
  { id: 'pricing', key: 'landing.nav.pricing' },
  { id: 'faq', key: 'landing.nav.faq' },
]

/** 尾幅 CTA + 页脚（品牌 / 导航 / 里程碑 / 版本） */
export default function LandingFooter() {
  const navigate = useNavigate()
  const t = useT()
  return (
    <footer>
      {/* 尾幅 CTA */}
      <section className="border-y text-center py-20" style={{ borderColor: 'var(--line)', background: 'var(--bg2)' }}>
        <div className="label" style={{ color: 'var(--acc)' }}>
          {t('landing.footer.ctaLabel')}
        </div>
        <h2 className="text-[32px] font-extrabold tracking-tight mt-3">{t('landing.footer.ctaTitle')}</h2>
        <p className="text-[13px] mt-3" style={{ color: 'var(--muted)' }}>
          {t('landing.footer.ctaDesc')}
        </p>
        <button className="btn btn-acc !px-8 !py-3 !text-[13px] mt-8" onClick={() => navigate('/login')}>
          {t('landing.footer.ctaButton')}
        </button>
      </section>

      {/* 页脚主体 */}
      <div className="max-w-[1080px] mx-auto px-6 py-14 grid md:grid-cols-[1.4fr_1fr_1.2fr] gap-10">
        <div>
          <div className="flex items-center gap-2.5">
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
              <rect x="1" y="1" width="20" height="20" stroke="#00ff2c" strokeWidth="2" />
              <rect x="6" y="9" width="3" height="7" fill="#fff" />
              <rect x="11" y="5" width="3" height="11" fill="#00ff2c" />
            </svg>
            <div className="text-[15px] font-extrabold tracking-tight">{t('landing.footer.brand')}</div>
          </div>
          <p className="text-[12px] mt-4 leading-relaxed" style={{ color: 'var(--muted)' }}>
            {t('landing.footer.about')}
          </p>
          <p className="text-[11px] mt-4" style={{ color: 'var(--dim)' }}>
            {t('landing.footer.meta', { v: LANDING_VERSION })}
          </p>
        </div>
        <div>
          <div className="label">{t('landing.footer.col.product')}</div>
          <div className="mt-4 space-y-2.5">
            <button className="block text-[12px] hover:text-white transition-colors cursor-pointer" style={{ color: 'var(--muted)' }} onClick={() => navigate('/login')}>
              {t('landing.footer.enterStudio')}
            </button>
            {FOOTER_LINKS.map((l) => (
              <button
                key={l.id}
                className="block text-[12px] hover:text-white transition-colors cursor-pointer"
                style={{ color: 'var(--muted)' }}
                onClick={() => scrollToSection(l.id)}
              >
                {t(l.key)}
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="label">{t('landing.footer.col.milestones')}</div>
          <div className="mt-4 space-y-2">
            {MILESTONES.map((m, i) => (
              <div key={m.ver} className="flex gap-3 text-[11px]">
                <span className="num font-bold flex-none" style={{ color: i === MILESTONES.length - 1 ? 'var(--acc)' : 'var(--dim)' }}>
                  {m.ver}
                </span>
                <span style={{ color: 'var(--muted)' }}>{t(m.title)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="border-t" style={{ borderColor: 'var(--line)' }}>
        <div className="max-w-[1080px] mx-auto px-6 py-5 flex flex-wrap items-center justify-between gap-3 text-[11px]" style={{ color: 'var(--dim)' }}>
          <span>{t('landing.footer.copyright', { n: CHANNELS.length })}</span>
          <span className="num">{LANDING_VERSION}</span>
        </div>
      </div>
    </footer>
  )
}
