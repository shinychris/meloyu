import type {
  CompleteTagsResult,
  LyricsGenerateResult,
  RhymeCheckResult,
} from '../../types/api'
import { useT, getLocale } from '../../i18n'
import { sectionLabel } from '../../lib/format'

interface AnalysisPanelProps {
  gen: LyricsGenerateResult | null
  rhyme: RhymeCheckResult | null
  tagInfo: CompleteTagsResult | null
  changes: Array<{ line_no: number; before: string; after: string }>
  onBackStudio: () => void
}

/** 歌词助手右侧面板：结构建议 / 润色记录 / 重音对齐 / 韵脚（数据来自接口响应） */
export default function AnalysisPanel({ gen, rhyme, tagInfo, changes, onBackStudio }: AnalysisPanelProps) {
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
      <div className="text-[12px] leading-relaxed mt-2" style={{ color: 'var(--muted)' }}>
        {gen && gen.structure.length > 0
          ? gen.structure
              .map((s) => t('lyrics.panel.sectionCount', { section: sectionLabel(s.section), n: s.line_count }))
              .join(' · ')
          : t('lyrics.panel.structureDefault')}
        {tagInfo && (
          <div className="mt-2" style={{ color: 'var(--dim)' }}>
            {t('lyrics.panel.tagDetect', {
              tags: tagInfo.detected.map((d) => sectionLabel(d.section)).join(' / ') || t('lyrics.panel.none'),
            })}
          </div>
        )}
      </div>

      {changes.length > 0 && (
        <>
          <div className="label mt-6">{t('lyrics.panel.polishLog')}</div>
          <div className="mt-2 space-y-2 text-[11px] leading-relaxed" style={{ color: 'var(--muted)' }}>
            {changes.slice(0, 8).map((c) => (
              <div key={c.line_no}>
                <span className="num" style={{ color: 'var(--dim)' }}>L{c.line_no}</span>{' '}
                <span style={{ textDecoration: 'line-through', color: 'var(--dim)' }}>{c.before}</span>
                {' → '}
                <span style={{ color: 'var(--txt)' }}>{c.after}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="label mt-6">{t('lyrics.panel.stress')}</div>
      <div className="mt-2 space-y-2 text-[12px]">
        {stressIssues.length === 0 && otherIssues.length === 0 ? (
          <div className="flex items-center gap-2">
            <span className="dot" style={{ background: rhyme ? 'var(--acc)' : 'var(--dim)' }}></span>
            <span style={{ color: 'var(--muted)' }}>
              {rhyme ? t('lyrics.panel.stressOk') : t('lyrics.panel.stressPending')}
            </span>
          </div>
        ) : (
          <>
            {stressIssues.map((s, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="dot mt-1.5" style={{ background: 'var(--warn)' }}></span>
                <span style={{ color: 'var(--muted)' }}>{s.message}</span>
              </div>
            ))}
            {otherIssues.map((s, i) => (
              <div key={`o${i}`} className="flex items-start gap-2">
                <span className="dot mt-1.5" style={{ background: 'var(--warn)' }}></span>
                <span style={{ color: 'var(--muted)' }}>{s.message}</span>
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
        {rhymeChips.length === 0
          ? (getLocale() === 'zh'
              ? ['台 ai', '白 ai', '待 ai', '轻 in', '心 in', '音 in']
              : ['ai', 'in', 'ing', 'an', 'ou', 'ei']
          ).map((c) => (
              <span key={c} className="chip" style={{ opacity: 0.5 }}>{c}</span>
            ))
          : rhymeChips.map((c, i) => <span key={i} className="chip">{c}</span>)}
      </div>
      <div className="mt-6">
        <button className="btn btn-ghost text-[11px] w-full" onClick={onBackStudio}>
          {t('lyrics.panel.backStudio')}
        </button>
      </div>
    </div>
  )
}
