import type {
  CompleteTagsResult,
  LyricsGenerateResult,
  RhymeCheckResult,
} from '../../types/api'
import { SECTION_ZH } from '../../lib/format'

interface AnalysisPanelProps {
  gen: LyricsGenerateResult | null
  rhyme: RhymeCheckResult | null
  tagInfo: CompleteTagsResult | null
  changes: Array<{ line_no: number; before: string; after: string }>
  onBackStudio: () => void
}

/** 歌词助手右侧面板：结构建议 / 润色记录 / 重音对齐 / 韵脚（数据来自接口响应） */
export default function AnalysisPanel({ gen, rhyme, tagInfo, changes, onBackStudio }: AnalysisPanelProps) {
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
      <div className="label">结构建议</div>
      <div className="text-[12px] leading-relaxed mt-2" style={{ color: 'var(--muted)' }}>
        {gen && gen.structure.length > 0
          ? gen.structure.map((s) => `${SECTION_ZH[s.section]} ${s.line_count} 行`).join(' · ')
          : '副歌核心句建议重复 2–3 次；桥段可降半音营造对比，末副歌回升。'}
        {tagInfo && (
          <div className="mt-2" style={{ color: 'var(--dim)' }}>
            标签检测：{tagInfo.detected.map((d) => SECTION_ZH[d.section]).join(' / ') || '无'}
          </div>
        )}
      </div>

      {changes.length > 0 && (
        <>
          <div className="label mt-6">润色记录</div>
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

      <div className="label mt-6">重音对齐</div>
      <div className="mt-2 space-y-2 text-[12px]">
        {stressIssues.length === 0 && otherIssues.length === 0 ? (
          <div className="flex items-center gap-2">
            <span className="dot" style={{ background: rhyme ? 'var(--acc)' : 'var(--dim)' }}></span>
            <span style={{ color: 'var(--muted)' }}>
              {rhyme ? '重音落拍正常' : '运行「押韵 / 重音检查」后显示'}
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

      <div className="label mt-6">韵脚{rhyme ? ` · 主韵 ${rhyme.main_rhyme_group}` : ''}</div>
      <div className="flex flex-wrap gap-1.5 mt-2">
        {rhymeChips.length === 0
          ? ['台 ai', '白 ai', '待 ai', '轻 in', '心 in', '音 in'].map((t) => (
              <span key={t} className="chip" style={{ opacity: 0.5 }}>{t}</span>
            ))
          : rhymeChips.map((t, i) => <span key={i} className="chip">{t}</span>)}
      </div>
      <div className="mt-6">
        <button className="btn btn-ghost text-[11px] w-full" onClick={onBackStudio}>
          返回工作台 →
        </button>
      </div>
    </div>
  )
}
