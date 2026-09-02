import { useNavigate } from 'react-router-dom'
import { useT, type TranslationKey } from '../../i18n'
import LangSwitch from '../common/LangSwitch'

const ANCHORS: Array<{ id: string; key: TranslationKey }> = [
  { id: 'features', key: 'landing.nav.features' },
  { id: 'channels', key: 'landing.nav.channels' },
  { id: 'models', key: 'landing.nav.models' },
  { id: 'showcase', key: 'landing.nav.showcase' },
  { id: 'pricing', key: 'landing.nav.pricing' },
  { id: 'faq', key: 'landing.nav.faq' },
]

export function scrollToSection(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

/** 落地页顶部导航：logo + 锚点（HashRouter 下锚点用 JS 滚动，不用 href="#"）+ 注册 CTA + 语言切换 */
export default function LandingNav() {
  const navigate = useNavigate()
  const t = useT()
  return (
    <header
      className="sticky top-0 z-40 border-b backdrop-blur-sm"
      style={{ borderColor: 'var(--line)', background: 'rgba(14,14,14,.92)' }}
    >
      <div className="max-w-[1080px] mx-auto px-6 h-[60px] flex items-center gap-8">
        <div className="flex items-center gap-2.5 flex-none">
          <svg width="24" height="24" viewBox="0 0 22 22" fill="none">
            <rect x="1" y="1" width="20" height="20" stroke="#00ff2c" strokeWidth="2" />
            <rect x="6" y="9" width="3" height="7" fill="#fff" />
            <rect x="11" y="5" width="3" height="11" fill="#00ff2c" />
          </svg>
          <div>
            <div className="text-[15px] font-extrabold tracking-tight leading-none">MELOYU</div>
            <div className="text-[9px] tracking-[.18em] uppercase mt-0.5" style={{ color: 'var(--dim)' }}>
              {t('landing.nav.brandSub')}
            </div>
          </div>
        </div>
        <nav className="hidden md:flex items-center gap-6 flex-1 text-[12px]" style={{ color: 'var(--muted)' }}>
          {ANCHORS.map((a) => (
            <button
              key={a.id}
              className="hover:text-white transition-colors cursor-pointer"
              onClick={() => scrollToSection(a.id)}
            >
              {t(a.key)}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-3 ml-auto">
          <LangSwitch />
          <button
            className="hidden sm:block text-[12px] cursor-pointer transition-colors"
            style={{ color: 'var(--muted)' }}
            onClick={() => navigate('/login')}
          >
            {t('landing.nav.login')}
          </button>
          <button className="btn btn-acc !py-2" onClick={() => navigate('/login')}>
            {t('landing.nav.cta')}
          </button>
        </div>
      </div>
    </header>
  )
}
