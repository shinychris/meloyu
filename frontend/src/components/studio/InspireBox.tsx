import { useState } from 'react'
import { useMetaStore } from '../../stores/meta'
import { useStudioStore } from '../../stores/studio'
import { toast } from '../../stores/toast'
import { useT, type TranslationKey } from '../../i18n'

const GROUPS: Array<{ key: 'scene' | 'mood' | 'genre' | 'inst'; label: TranslationKey; source: 'scenes' | 'moods' | 'genres' | 'instruments' }> = [
  { key: 'scene', label: 'studio.inspire.scene', source: 'scenes' },
  { key: 'mood', label: 'studio.inspire.mood', source: 'moods' },
  { key: 'genre', label: 'studio.inspire.genre', source: 'genres' },
  { key: 'inst', label: 'studio.inspire.inst', source: 'instruments' },
]

/** 折叠态每组展示的词条数（词表扩全主流后按组展开，避免长卡片淹没工作台） */
const COLLAPSED_COUNT = 10

/** 灵感指引卡：点选组合自动组装风格描述（数据来自 /system/meta inspiration） */
export default function InspireBox() {
  const t = useT()
  const inspiration = useMetaStore((s) => s.meta.inspiration)
  const inspire = useStudioStore((s) => s.inspire)
  const { setInspire, applyInspireToPrompt, markStep, logOp } = useStudioStore()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const pick = (group: (typeof GROUPS)[number], value: string) => {
    const next = { ...inspire, [group.key]: inspire[group.key] === value ? '' : value }
    setInspire({ [group.key]: next[group.key] })
    if (next[group.key]) {
      applyInspireToPrompt(next)
      markStep(1)
    }
  }

  const random = () => {
    const next = { scene: '', mood: '', genre: '', inst: '' }
    for (const g of GROUPS) {
      const list = inspiration[g.source]
      if (list.length > 0) next[g.key] = list[Math.floor(Math.random() * list.length)]
    }
    useStudioStore.setState({ inspire: next })
    applyInspireToPrompt(next)
    markStep(1)
    logOp(
      t('studio.log.inspire', {
        detail: [next.genre, next.mood, next.inst, next.scene].filter(Boolean).join(' / '),
      }),
    )
    toast(t('studio.toast.inspireRandom'))
  }

  return (
    <div className="card mt-4 p-3.5" id="inspireBox">
      <div className="flex items-center justify-between">
        <div className="label" style={{ color: 'var(--acc)' }}>
          {t('studio.inspire.title')}
        </div>
        <button className="text-[10px] font-bold" style={{ color: 'var(--acc)' }} onClick={random}>
          {t('studio.inspire.random')}
        </button>
      </div>
      <div className="text-[10px] mt-1.5 mb-2" style={{ color: 'var(--dim)' }}>
        {t('studio.inspire.hint')}
      </div>
      {GROUPS.map((g) => {
        const list = inspiration[g.source]
        const open = expanded[g.key] || list.length <= COLLAPSED_COUNT
        let shown = open ? list : list.slice(0, COLLAPSED_COUNT)
        if (!open && inspire[g.key] && !shown.includes(inspire[g.key])) {
          // 折叠时选中项落在折叠区：附加展示，保证选中态可见
          shown = [...shown, inspire[g.key]]
        }
        const hiddenCount = list.length - COLLAPSED_COUNT
        return (
          <div key={g.key}>
            <div className={`text-[10px] ${g.key === 'scene' ? '' : 'mt-2.5'} mb-1`} style={{ color: 'var(--dim)' }}>
              {t(g.label)}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {shown.map((item) => (
                <span
                  key={item}
                  className={`chip ${inspire[g.key] === item ? 'on' : ''}`}
                  onClick={() => pick(g, item)}
                >
                  {item}
                </span>
              ))}
              {list.length > COLLAPSED_COUNT && (
                <span
                  className="chip"
                  style={{ color: 'var(--acc)' }}
                  onClick={() => setExpanded((s) => ({ ...s, [g.key]: !s[g.key] }))}
                >
                  {open ? t('studio.inspire.less') : t('studio.inspire.more', { n: hiddenCount })}
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
