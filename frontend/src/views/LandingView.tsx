import { useEffect } from 'react'
import { useI18nStore, useT } from '../i18n'
import LandingNav from '../components/landing/LandingNav'
import LandingHero from '../components/landing/LandingHero'
import LandingWorkFlow from '../components/landing/LandingWorkFlow'
import LandingCapabilities from '../components/landing/LandingCapabilities'
import LandingChannels from '../components/landing/LandingChannels'
import LandingModels from '../components/landing/LandingModels'
import LandingShowcase from '../components/landing/LandingShowcase'
import LandingAudience from '../components/landing/LandingAudience'
import LandingPricing from '../components/landing/LandingPricing'
import LandingFaq from '../components/landing/LandingFaq'
import LandingFooter from '../components/landing/LandingFooter'

/** 产品落地页（公共路由，登录墙之外）：全套展示信息 + 注册入口 */
export default function LandingView() {
  const t = useT()
  const locale = useI18nStore((s) => s.locale)

  // 挂载 / 语言切换时设置落地页标题，卸载时恢复应用标题（依赖 locale 保证切语言即时生效）
  useEffect(() => {
    document.title = t('landing.title')
    return () => {
      document.title = t('app.title')
    }
  }, [locale, t])

  return (
    <div className="h-screen overflow-y-auto scroll-smooth view bg-bg">
      <LandingNav />
      <LandingHero />
      <div className="max-w-[1080px] mx-auto px-6 space-y-20 md:space-y-28 py-24">
        <LandingWorkFlow />
        <LandingCapabilities />
        <LandingChannels />
        <LandingModels />
        <LandingShowcase />
        <LandingAudience />
        {/* 章节「功能 → 商业化」分隔 */}
        <div aria-hidden="true" className="border-t border-line" />
        <LandingPricing />
        <LandingFaq />
      </div>
      <LandingFooter />
    </div>
  )
}
