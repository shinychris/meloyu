import { useState } from 'react'
import { SECTIONS } from './modelcenter/shared'
import { ModelCenterProvider } from './modelcenter/context'
import OverviewSection from './modelcenter/OverviewSection'
import ComponentsSection from './modelcenter/ComponentsSection'
import LyricsSection from './modelcenter/LyricsSection'
import MusicSection from './modelcenter/MusicSection'
import CatalogSection from './modelcenter/CatalogSection'
import LibrarySection from './modelcenter/LibrarySection'
import OpsSection from './modelcenter/OpsSection'
import { useT } from '../i18n'

/**
 * 模型中心（契约 §5.8）：左侧分类导航 + 概览/组件中心/歌词引擎/歌曲引擎/
 * 开源目录/本地模型库/操作记录。
 * F-FE-09：按 section 拆分为 modelcenter/ 下子组件，共享状态收敛到
 * ModelCenterProvider（行为与视觉与拆分前一致）。
 * 分区为点选切换：一次只渲染选中分区，不滚动；initialSection 供深链/测试
 * 指定初始分区（非法值回退首分区）。
 */
export default function ModelCenterView({ initialSection }: { initialSection?: string }) {
  const t = useT()
  const [active, setActive] = useState(() =>
    SECTIONS.some((s) => s.id === initialSection) ? initialSection! : SECTIONS[0].id,
  )

  // 分区内跳转（概览「去配置」等）：与导航点选同语义，切分区而非滚动
  const jump = (id: string) => setActive(id)

  return (
    <ModelCenterProvider>
      <div className="view h-full overflow-y-auto">
        <div className="px-4 md:px-8 py-8">
          <div className="label">{t('models.label')}</div>
          <h1 className="text-3xl font-extrabold tracking-tight mt-2">{t('models.title')}</h1>
          <p className="text-sm mt-2 text-dim">
            {t('models.intro')}
          </p>

          <div className="flex flex-col lg:flex-row lg:items-start gap-5 lg:gap-8 mt-6">
            {/* 分区点选导航：移动端横向 chips（点选切换后无滚动，必须有切换入口），lg+ 左侧竖排 */}
            <nav className="lg:w-[168px] lg:flex-none lg:sticky lg:top-6">
              <div className="flex flex-wrap gap-2 lg:hidden">
                {SECTIONS.map((s) => {
                  const on = active === s.id
                  return (
                    <button
                      key={s.id}
                      className={`chip ${on ? 'on' : ''}`}
                      aria-pressed={on}
                      onClick={() => setActive(s.id)}
                    >
                      {t(s.labelKey)}
                    </button>
                  )
                })}
              </div>
              <div className="hidden lg:block py-1">
                {SECTIONS.map((s) => {
                  const on = active === s.id
                  return (
                    <button
                      key={s.id}
                      aria-current={on || undefined}
                      className={`w-full text-left px-3 py-2 text-sm transition-colors flex items-center gap-2 border-l-2 ${
                        on ? 'text-acc font-bold bg-bg-2 border-acc' : 'text-muted font-normal border-transparent'
                      }`}
                      onClick={() => setActive(s.id)}
                    >
                      {t(s.labelKey)}
                    </button>
                  )
                })}
              </div>
            </nav>

            <div className="flex-1 min-w-0">
              {active === 'mc-overview' && <OverviewSection jump={jump} />}
              {active === 'mc-components' && <ComponentsSection />}
              {active === 'mc-lyrics' && <LyricsSection />}
              {active === 'mc-music' && <MusicSection />}
              {active === 'mc-catalog' && <CatalogSection />}
              {active === 'mc-library' && <LibrarySection />}
              {active === 'mc-ops' && <OpsSection />}
            </div>
          </div>
        </div>
      </div>
    </ModelCenterProvider>
  )
}
