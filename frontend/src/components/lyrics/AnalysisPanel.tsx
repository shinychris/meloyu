import type { CompleteTagsResult, RhymeCheckResult } from '../../types/api'
import type { StructureSection } from '../../lib/structure'
import { useT } from '../../i18n'
import { sectionLabel } from '../../lib/format'

interface AnalysisPanelProps {
  /** 编辑器内容的实时结构解析（F-04：随编辑刷新，不再用上次生成响应的快照） */
  structure: StructureSection[]
  rhyme: RhymeCheckResult | null
  tagInfo: CompleteTagsResult | null
  changes: Array<{ line_no: number; before: string; after: string }>
  onBackStudio: () => void
}

/** 歌词助手右侧面板：结构建议 / 润色记录 / 重音对齐 / 韵脚（数据来自接口响应） */
export default function AnalysisPanel({ structure, rhyme, tagInfo, changes, onBackStudio }: AnalysisPanelProps) {
  const t = useT()
  const stressIssues = rhyme?.suggestions.filter((s) => s.type === 'stress') ?? []
  const otherIssues = rhyme?.suggestions.filter((s) => s.type !== 'stress') ?? []
  const rhymeChips: string[] = []
  if (rhyme) {
    for (const sec of rhyme.sections) {
      for (const line of sec.lines) {
        rhymeChips.push(`${line.tail_char} ${line.rhyme_group}`)
      }
    }
  }

  return (
    <div className="px-6 py-5 overflow-y-auto">
      <div className="label">{t('lyrics.panel.structure')}</div>
      <div className="text-sm leading-relaxed mt-2 text-muted">
        {structure.length > 0
          ? structure
              .map((s) => t('lyrics.panel.sectionCount', { section: sectionLabel(s.section), n: s.line_count }))
              .join(' · ')
          : t('lyrics.panel.structureDefault')}
        {tagInfo && (
          <div className="mt-2 text-dim">
            {t('lyrics.panel.tagDetect', {
              tags: tagInfo.detected.map((d) => sectionLabel(d.section)).join(' / ') || t('lyrics.panel.none'),
            })}
          </div>
        )}
      </div>

      {changes.length > 0 && (
        <>
          <div className="label mt-6">{t('lyrics.panel.polishLog')}</div>
          <div className="mt-2 space-y-2 text-xs leading-relaxed text-muted">
            {changes.slice(0, 8).map((c) => (
              <div key={c.line_no}>
                <span className="num text-dim">L{c.line_no}</span>{' '}
                <span className="text-dim" style={{ textDecoration: 'line-through' }}>{c.before}</span>
                {' → '}
                <span className="text-txt">{c.after}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="label mt-6">{t('lyrics.panel.stress')}</div>
      <div className="mt-2 space-y-2 text-sm">
        {stressIssues.length === 0 && otherIssues.length === 0 ? (
          <div className="flex items-center gap-2">
            <span className="dot" style={{ background: rhyme ? 'var(--acc)' : 'var(--dim)' }}></span>
            <span className="text-muted">
              {rhyme ? t('lyrics.panel.stressOk') : t('lyrics.panel.stressPending')}
            </span>
          </div>
        ) : (
          <>
            {stressIssues.map((s, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="dot mt-1.5" style={{ background: 'var(--warn)' }}></span>
                <span className="text-muted">{s.message}</span>
              </div>
            ))}
            {otherIssues.map((s, i) => (
              <div key={`o${i}`} className="flex items-start gap-2">
                <span className="dot mt-1.5" style={{ background: 'var(--warn)' }}></span>
                <span className="text-muted">{s.message}</span>
              </div>
            ))}
          </>
        )}
      </div>

      <div className="label mt-6">
        {t('lyrics.panel.rhyme')}
        {rhyme ? t('lyrics.panel.rhymeMain', { group: rhyme.main_rhyme_group }) : ''}
      </div>
      <div className="flex flex-wrap gap-1.5 mt-2">
        {/* F-FE-27：无数据展示 i18n 空态说明，不再渲染形似真实结果的硬编码示例 chips */}
        {rhymeChips.length === 0 ? (
          <span className="text-2xs text-dim">{t('lyrics.panel.rhymeEmpty')}</span>
        ) : (
          rhymeChips.map((c, i) => <span key={i} className="chip">{c}</span>)
        )}
      </div>
      <div className="mt-6">
        <button className="btn btn-ghost w-full" onClick={onBackStudio}>
          {t('lyrics.panel.backStudio')}
        </button>
      </div>
    </div>
  )
}
