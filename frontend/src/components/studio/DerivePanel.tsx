import { useMemo, useState } from 'react'
import type { Candidate, RegenSectionRequest } from '../../types/api'
import { formatClock, SECTION_LABEL, SECTION_ZH } from '../../lib/format'

export type DeriveKind = 'extend' | 'variant' | 'regen'

const EXTEND_PRESETS = [15, 30, 60] as const

/** 同段出现次序（契约 v1.2 §5.7 occurrence，1 起始）：structure 前缀中与 pos 同 section 的个数 + 1 */
function occurrenceNo(structure: Candidate['structure'], pos: number): number {
  let n = 0
  for (let i = 0; i < pos; i++) {
    if (structure[i].section === structure[pos].section) n++
  }
  return n + 1
}

interface DerivePanelProps {
  kind: DeriveKind
  candidate: Candidate
  busy: boolean
  onSubmitExtend: (seconds: number) => void
  onSubmitVariant: (stylePrompt: string) => void
  onSubmitRegen: (req: RegenSectionRequest) => void
  onClose: () => void
}

const KIND_TITLE: Record<DeriveKind, string> = {
  extend: 'Extend / 延长',
  variant: 'Variant / 变体',
  regen: 'Regen / 段落重生成',
}

/**
 * 候选派生操作面板（V1.1，契约 §5.5~5.7）：
 * - extend：选续写秒数（15/30/60 预设，契约范围 15~60）
 * - variant：新风格描述输入（可空 = 自动换风格）
 * - regen：从候选 structure 列出段落（多次出现以 #n 区分，带起止秒）供选择
 * 提交后由父组件交给 stores/studio.ts 复用生成轮询。
 */
export default function DerivePanel({
  kind,
  candidate,
  busy,
  onSubmitExtend,
  onSubmitVariant,
  onSubmitRegen,
  onClose,
}: DerivePanelProps) {
  const [seconds, setSeconds] = useState<number>(30)
  const [stylePrompt, setStylePrompt] = useState('')
  const [selectedSeg, setSelectedSeg] = useState<number | null>(null)

  const sectionCounts = useMemo(() => {
    const m = new Map<string, number>()
    for (const seg of candidate.structure) m.set(seg.section, (m.get(seg.section) ?? 0) + 1)
    return m
  }, [candidate.structure])

  const submitRegen = () => {
    if (selectedSeg == null) return
    onSubmitRegen({
      section: candidate.structure[selectedSeg].section,
      occurrence: occurrenceNo(candidate.structure, selectedSeg), // 1 起始，显式发送
    })
  }

  return (
    <div className="mx-4 mb-3 border p-3 pop" style={{ borderColor: 'var(--line)', background: 'var(--bg3)' }}>
      <div className="flex items-center justify-between">
        <div className="label">{KIND_TITLE[kind]}</div>
        <button className="iconbtn !w-6 !h-6" title="关闭" onClick={onClose} disabled={busy}>
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M3.5 3.5l9 9M12.5 3.5l-9 9" />
          </svg>
        </button>
      </div>

      {kind === 'extend' && (
        <>
          <div className="text-[11px] mt-2" style={{ color: 'var(--dim)' }}>
            从结尾续写生成新子版本（消耗积分，失败自动退还）
          </div>
          <div className="flex items-center gap-1.5 mt-2 flex-wrap">
            {EXTEND_PRESETS.map((s) => (
              <span key={s} className={`chip ${seconds === s ? 'on' : ''}`} onClick={() => setSeconds(s)}>
                {`+${s}s`}
              </span>
            ))}
            <span style={{ flex: 1 }}></span>
            <button
              className="btn btn-acc !py-1 !px-3 text-[11px]"
              disabled={busy}
              onClick={() => onSubmitExtend(seconds)}
            >
              {busy ? '提交中…' : `延长 ${seconds} 秒`}
            </button>
          </div>
        </>
      )}

      {kind === 'variant' && (
        <>
          <div className="text-[11px] mt-2" style={{ color: 'var(--dim)' }}>
            保持结构与歌词不变，仅更换风格，生成新子版本
          </div>
          <input
            type="text"
            value={stylePrompt}
            maxLength={500}
            placeholder="新风格描述（可留空 = 自动换风格）"
            aria-label="新风格描述"
            autoFocus
            onChange={(e) => setStylePrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !busy) onSubmitVariant(stylePrompt.trim())
            }}
            className="mt-2 w-full !text-[12px]"
            style={{ padding: '6px 10px' }}
          />
          <div className="flex justify-end mt-2">
            <button
              className="btn btn-acc !py-1 !px-3 text-[11px]"
              disabled={busy}
              onClick={() => onSubmitVariant(stylePrompt.trim())}
            >
              {busy ? '提交中…' : '生成变体'}
            </button>
          </div>
        </>
      )}

      {kind === 'regen' && (
        <>
          <div className="text-[11px] mt-2" style={{ color: 'var(--dim)' }}>
            仅重生成所选段落，其余段落保持原样；同名段落以 #次序 区分
          </div>
          {candidate.structure.length === 0 ? (
            <div className="text-[11px] mt-2" style={{ color: 'var(--warn)' }}>
              该候选无结构信息，无法定位段落
            </div>
          ) : (
            <div className="flex gap-1.5 mt-2 flex-wrap">
              {candidate.structure.map((seg, i) => {
                const count = sectionCounts.get(seg.section) ?? 1
                const occ = occurrenceNo(candidate.structure, i)
                const selected = selectedSeg === i
                return (
                  <span
                    key={i}
                    className={`chip ${selected ? 'on' : ''}`}
                    title={`${SECTION_ZH[seg.section]} · ${seg.bars} 小节 · ${formatClock(seg.start_sec)}–${formatClock(seg.end_sec)}`}
                    onClick={() => setSelectedSeg(i)}
                  >
                    {`${SECTION_LABEL[seg.section]}${count > 1 ? `#${occ}` : ''}`}
                    <span className="num ml-1" style={{ fontSize: 9, color: selected ? undefined : 'var(--dim)' }}>
                      {`${formatClock(seg.start_sec)}–${formatClock(seg.end_sec)}`}
                    </span>
                  </span>
                )
              })}
            </div>
          )}
          <div className="flex justify-end mt-2">
            <button
              className="btn btn-acc !py-1 !px-3 text-[11px]"
              disabled={busy || selectedSeg == null}
              title={selectedSeg == null ? '先选择一个段落' : undefined}
              onClick={submitRegen}
            >
              {busy ? '提交中…' : '重生成该段'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
