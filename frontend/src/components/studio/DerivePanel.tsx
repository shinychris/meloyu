import { useMemo, useState } from 'react'
import type { Candidate, RegenSectionRequest } from '../../types/api'
import { formatClock, sectionLabel } from '../../lib/format'
import { useSessionStore } from '../../stores/session'
import { useT, type TranslationKey } from '../../i18n'

export type DeriveKind = 'extend' | 'variant' | 'regen'

const EXTEND_PRESETS = [15, 30, 60] as const

/** 同段出现次序（occurrence，1 起始）：structure 前缀中与 pos 同 section 的个数 + 1 */
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

const KIND_TITLE: Record<DeriveKind, TranslationKey> = {
  extend: 'studio.derive.extend.title',
  variant: 'studio.derive.variant.title',
  regen: 'studio.derive.regen.title',
}

/**
 * 候选派生操作面板（V1.1）：
 * - extend：选续写秒数（15/30/60 预设，范围 15~60）
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
  const t = useT()
  // license（桌面买断）模式：续写提示不再出现积分语义（v0.17.0）
  const isLicense = useSessionStore((s) => s.license?.billing_mode === 'license')
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
    <div className="mx-4 mb-3 border p-3 pop border-line bg-bg-3">
      <div className="flex items-center justify-between">
        <div className="label">{t(KIND_TITLE[kind])}</div>
        <button className="iconbtn !w-6 !h-6" title={t('common.close')} onClick={onClose} disabled={busy}>
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M3.5 3.5l9 9M12.5 3.5l-9 9" />
          </svg>
        </button>
      </div>

      {kind === 'extend' && (
        <>
          <div className="text-xs mt-2 text-dim">
            {t(isLicense ? 'studio.derive.extend.hintLocal' : 'studio.derive.extend.hint')}
          </div>
          <div className="flex items-center gap-1.5 mt-2 flex-wrap">
            {EXTEND_PRESETS.map((s) => (
              <button key={s} type="button" className={`chip ${seconds === s ? 'on' : ''}`} onClick={() => setSeconds(s)}>
                {`+${s}s`}
              </button>
            ))}
            <span style={{ flex: 1 }}></span>
            <button
              className="btn btn-acc btn-sm"
              disabled={busy}
              onClick={() => onSubmitExtend(seconds)}
            >
              {busy ? t('studio.derive.submitting') : t('studio.derive.extend.submit', { n: seconds })}
            </button>
          </div>
        </>
      )}

      {kind === 'variant' && (
        <>
          <div className="text-xs mt-2 text-dim">
            {t('studio.derive.variant.hint')}
          </div>
          <input
            type="text"
            value={stylePrompt}
            maxLength={500}
            placeholder={t('studio.derive.variant.placeholder')}
            aria-label={t('studio.derive.variant.aria')}
            autoFocus
            onChange={(e) => setStylePrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !busy) onSubmitVariant(stylePrompt.trim())
            }}
            className="mt-2 w-full !text-sm"
            style={{ padding: '6px 10px' }}
          />
          <div className="flex justify-end mt-2">
            <button
              className="btn btn-acc btn-sm"
              disabled={busy}
              onClick={() => onSubmitVariant(stylePrompt.trim())}
            >
              {busy ? t('studio.derive.submitting') : t('studio.derive.variant.submit')}
            </button>
          </div>
        </>
      )}

      {kind === 'regen' && (
        <>
          <div className="text-xs mt-2 text-dim">
            {t('studio.derive.regen.hint')}
          </div>
          {candidate.structure.length === 0 ? (
            <div className="text-xs mt-2 text-warn">
              {t('studio.derive.regen.empty')}
            </div>
          ) : (
            <div className="flex gap-1.5 mt-2 flex-wrap">
              {candidate.structure.map((seg, i) => {
                const count = sectionCounts.get(seg.section) ?? 1
                const occ = occurrenceNo(candidate.structure, i)
                const selected = selectedSeg === i
                return (
                  <button
                    key={i}
                    type="button"
                    className={`chip ${selected ? 'on' : ''}`}
                    title={t('studio.derive.seg', {
                      section: sectionLabel(seg.section),
                      bars: seg.bars,
                      range: `${formatClock(seg.start_sec)}–${formatClock(seg.end_sec)}`,
                    })}
                    onClick={() => setSelectedSeg(i)}
                  >
                    {`${sectionLabel(seg.section)}${count > 1 ? `#${occ}` : ''}`}
                    <span className={`num ml-1 text-2xs ${selected ? '' : 'text-dim'}`}>
                      {`${formatClock(seg.start_sec)}–${formatClock(seg.end_sec)}`}
                    </span>
                  </button>
                )
              })}
            </div>
          )}
          <div className="flex justify-end mt-2">
            <button
              className="btn btn-acc btn-sm"
              disabled={busy || selectedSeg == null}
              title={selectedSeg == null ? t('studio.derive.regen.pickFirst') : undefined}
              onClick={submitRegen}
            >
              {busy ? t('studio.derive.submitting') : t('studio.derive.regen.submit')}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
