import { useNavigate } from 'react-router-dom'
import { CHANNELS, LANDING_VERSION } from '../../lib/landing-data'
import { useT, type TranslationKey } from '../../i18n'
import { Logo } from '../common/Logo'
import { scrollToSection } from './LandingNav'

/** 页脚锚点导航（与顶部导航共用文案 key） */
const FOOTER_LINKS: Array<{ id: string; key: TranslationKey }> = [
  { id: 'features', key: 'landing.nav.features' },
  { id: 'channels', key: 'landing.nav.channels' },
  { id: 'models', key: 'landing.nav.models' },
  { id: 'pricing', key: 'landing.nav.pricing' },
  { id: 'faq', key: 'landing.nav.faq' },
]

/** 尾幅 CTA + 页脚（品牌 / 导航 / 版本） */
export default function LandingFooter() {
  const navigate = useNavigate()
  const t = useT()
  return (
    <footer>
      {/* 尾幅 CTA */}
      <section className="border-y border-line bg-bg-2 text-center py-20">
        <div className="label" style={{ color: 'var(--acc)' }}>
          {t('landing.footer.ctaLabel')}
        </div>
        <h2 className="text-4xl font-extrabold tracking-tight mt-3">{t('landing.footer.ctaTitle')}</h2>
        <p className="text-base mt-3 text-muted">
          {t('landing.footer.ctaDesc')}
        </p>
        <button className="btn btn-acc btn-lg mt-8" onClick={() => navigate('/login')}>
          {t('landing.footer.ctaButton')}
        </button>
      </section>

      {/* 页脚主体 */}
      <div className="max-w-[1080px] mx-auto px-6 py-14 grid md:grid-cols-[1.6fr_1fr] gap-10">
        <div>
          <div className="flex items-center gap-2.5">
            <Logo size={22} />
            <div className="text-md font-extrabold tracking-tight">{t('landing.footer.brand')}</div>
          </div>
          <p className="text-sm mt-4 leading-relaxed text-muted">
            {t('landing.footer.about')}
          </p>
          <p className="text-xs mt-4 text-dim">
            {t('landing.footer.meta', { v: LANDING_VERSION })}
          </p>
        </div>
        <div>
          <div className="label">{t('landing.footer.col.product')}</div>
          <div className="mt-4 space-y-2.5">
            <button className="block text-sm text-muted hover:text-white transition-colors cursor-pointer" onClick={() => navigate('/login')}>
              {t('landing.footer.enterStudio')}
            </button>
            {FOOTER_LINKS.map((l) => (
              <button
                key={l.id}
                className="block text-sm text-muted hover:text-white transition-colors cursor-pointer"
                onClick={() => scrollToSection(l.id)}
              >
                {t(l.key)}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="border-t border-line">
        <div className="max-w-[1080px] mx-auto px-6 py-5 flex flex-wrap items-center justify-between gap-3 text-xs text-dim">
          <span>{t('landing.footer.copyright', { n: CHANNELS.length })}</span>
          <span className="num">{LANDING_VERSION}</span>
        </div>
      </div>
    </footer>
  )
}
