import { useNavigate } from 'react-router-dom'
import { useT, type TranslationKey } from '../../i18n'
import LangSwitch from '../common/LangSwitch'
import { useSiteMode } from './SiteMode'
import { Logo } from '../common/Logo'

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
  const site = useSiteMode()
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/90 backdrop-blur-md">
      <div className="px-4 sm:px-6 lg:px-10 2xl:px-16 h-[60px] flex items-center gap-8">
        <div className="flex items-center gap-2.5 flex-none">
          <Logo size={24} />
          <div>
            <div className="text-md font-extrabold tracking-tight leading-none">MELOYU</div>
            <div className="text-2xs tracking-[.18em] uppercase mt-0.5 text-dim">
              {t('landing.nav.brandSub')}
            </div>
          </div>
        </div>
        <nav className="hidden md:flex items-center gap-6 flex-1 text-sm text-muted">
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
          {!site && (
            <button
              className="hidden sm:block text-sm text-muted cursor-pointer transition-colors"
              onClick={() => navigate('/login')}
            >
              {t('landing.nav.login')}
            </button>
          )}
          <button className="btn btn-acc btn-sm" onClick={() => scrollToSection('pricing')}>
            {t('landing.nav.cta')}
          </button>
        </div>
      </div>
    </header>
  )
}
