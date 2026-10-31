import { SECTIONS } from './modelcenter/shared'
import { ModelCenterProvider } from './modelcenter/context'
import OverviewSection from './modelcenter/OverviewSection'
import ComponentsSection from './modelcenter/ComponentsSection'
import LyricsSection from './modelcenter/LyricsSection'
import MusicSection from './modelcenter/MusicSection'
import CatalogSection from './modelcenter/CatalogSection'
import LibrarySection from './modelcenter/LibrarySection'
import OpsSection from './modelcenter/OpsSection'
import { useScrollSpy } from '../lib/useScrollSpy'
import { useT } from '../i18n'

/**
 * 模型中心（契约 §5.8）：左侧分类导航 + 概览/组件中心/歌词引擎/歌曲引擎/
 * 开源目录/本地模型库/操作记录。
 * F-FE-09：按 section 拆分为 modelcenter/ 下子组件，共享状态收敛到
 * ModelCenterProvider（行为与视觉与拆分前一致）。
 */
export default function ModelCenterView() {
  const t = useT()
  const { scrollRef, activeSection, setActiveSection } = useScrollSpy(
    SECTIONS.map((s) => s.id),
    '-8% 0px -80% 0px',
  )

  const jump = (id: string) => {
    setActiveSection(id)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <ModelCenterProvider>
      <div className="view h-full overflow-y-auto" ref={scrollRef}>
        <div className="px-4 md:px-8 py-8">
          <div className="label">{t('models.label')}</div>
          <h1 className="text-3xl font-extrabold tracking-tight mt-2">{t('models.title')}</h1>
          <p className="text-sm mt-2 text-dim">
            {t('models.intro')}
          </p>

          <div className="flex items-start gap-8 mt-6">
            {/* 左侧分类导航 */}
            <aside className="w-[168px] flex-none sticky top-6 hidden lg:block">
              <div className="py-1">
                {SECTIONS.map((s) => {
                  const active = activeSection === s.id
                  return (
                    <button
                      key={s.id}
                      className={`w-full text-left px-3 py-2 text-sm transition-colors flex items-center gap-2 border-l-2 ${
                        active ? 'text-acc font-bold bg-bg-2 border-acc' : 'text-muted font-normal border-transparent'
                      }`}
                      onClick={() => jump(s.id)}
                    >
                      {t(s.labelKey)}
                    </button>
                  )
                })}
              </div>
            </aside>

            <div className="flex-1 min-w-0">
              <OverviewSection jump={jump} />
              <ComponentsSection />
              <LyricsSection />
              <MusicSection />
              <CatalogSection />
              <LibrarySection />
              <OpsSection />
            </div>
          </div>
        </div>
      </div>
    </ModelCenterProvider>
  )
}
