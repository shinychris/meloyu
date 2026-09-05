import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Candidate, Work } from '../types/api'
import { listWorks, getVersionTree } from '../api/works'
import { listCandidates, getTask, pitchEditCandidate } from '../api/generation'
import { apiGet } from '../api/client'
import { toast } from '../stores/toast'
import { useT } from '../i18n'

/** 词谱 json（meloyu.leadsheet/1.0）中与本视图相关的子集 */
interface LeadsheetNote {
  beat: number
  dur: number
  midi: number
  degree: string
  syllable: string
}
interface LeadsheetData {
  meta: { key: string; bpm: number; time_signature: string; beats_per_bar: number }
  bars: Array<{ bar: number; section: string; chord: string; notes: LeadsheetNote[] }>
  stats: { note_count: number; bar_count: number }
}

const PC_SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
const MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10]

function midiName(m: number): string {
  return `${PC_SHARP[((m % 12) + 12) % 12]}${Math.floor(m / 12) - 1}`
}

function scalePitchClasses(key: string): Set<number> {
  const [tonic, mode] = key.split(' ')
  const t = PC_SHARP.indexOf(tonic)
  const steps = mode === 'major' ? MAJOR_STEPS : MINOR_STEPS
  return new Set(steps.map((s) => (t + s) % 12))
}

/**
 * 旋律修调（/pitch，v0.11.0）：钢琴卷帘（词谱 json 的旋律音符）→
 * 选中音符 ↑/↓ 移调（半音）→ 可选吸附音阶 / 节奏量化（1/8·1/16）→
 * POST /candidates/{id}/pitch-edit（同 seed 确定性重渲染，子版本 source=pitch_edit）。
 */
export default function PitchView() {
  const t = useT()
  const [works, setWorks] = useState<Work[]>([])
  const [workId, setWorkId] = useState('')
  const [versionId, setVersionId] = useState('')
  const [candidate, setCandidate] = useState<Candidate | null>(null)
  const [ls, setLs] = useState<LeadsheetData | null>(null)
  const [edits, setEdits] = useState<Record<number, number>>({}) // noteIdx -> 累计 semi
  const [selected, setSelected] = useState<number | null>(null)
  const [quantize, setQuantize] = useState<'off' | '8' | '16'>('off')
  const [submitting, setSubmitting] = useState(false)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    listWorks({ page_size: 100 }).then((r) => setWorks(r.items)).catch(() => {})
  }, [])

  useEffect(() => {
    if (!workId) return
    getVersionTree(workId)
      .then((tree: { current_version_id: string | null }) =>
        setVersionId(tree.current_version_id ?? ''))
      .catch(() => setVersionId(''))
  }, [workId])

  const loadVersion = useCallback(async (vid: string) => {
    setLs(null)
    setEdits({})
    setSelected(null)
    try {
      const res = await listCandidates(vid)
      const cand = res.items.find((c) => c.adopted) ?? res.items[0]
      setCandidate(cand ?? null)
      if (!cand) return
      const data = await apiGet<LeadsheetData>(`/versions/${vid}/leadsheet?format=json`)
      setLs(data)
    } catch {
      /* 拦截器已 toast（外部候选 40901 等） */
    }
  }, [])

  useEffect(() => {
    if (versionId) void loadVersion(versionId)
  }, [versionId, loadVersion])

  const notes = useMemo<LeadsheetNote[]>(
    () => (ls ? ls.bars.flatMap((b) => b.notes) : []), [ls])

  const editedMidi = useCallback(
    (i: number, base: number) => base + (edits[i] ?? 0), [edits])

  // 键盘：↑/↓ 半音、Esc 取消
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (selected === null) return
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return
      if (e.key === 'ArrowUp' || e.key === '+') {
        e.preventDefault()
        bump(selected, 1)
      } else if (e.key === 'ArrowDown' || e.key === '-') {
        e.preventDefault()
        bump(selected, -1)
      } else if (e.key === 'Escape') {
        setSelected(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, edits])

  const bump = (idx: number, delta: number) => {
    setEdits((prev) => {
      const cur = prev[idx] ?? 0
      const next = Math.max(-12, Math.min(12, cur + delta))
      return { ...prev, [idx]: next }
    })
  }

  const snapToScale = () => {
    if (!ls) return
    const pcs = scalePitchClasses(ls.meta.key)
    const next: Record<number, number> = { ...edits }
    let snapped = 0
    notes.forEach((n, i) => {
      const midi = editedMidi(i, n.midi)
      if (pcs.has(((midi % 12) + 12) % 12)) return
      for (let d = 1; d <= 6; d++) {
        const up = midi + d
        if (pcs.has(((up % 12) + 12) % 12)) {
          next[i] = (next[i] ?? 0) + d
          snapped++
          break
        }
        const down = midi - d
        if (pcs.has(((down % 12) + 12) % 12)) {
          next[i] = (next[i] ?? 0) - d
          snapped++
          break
        }
      }
    })
    setEdits(next)
    toast(t(snapped > 0 ? 'pitch.toast.snapped' : 'pitch.toast.allInScale', { n: snapped }))
  }

  // 绘制钢琴卷帘
  useEffect(() => {
    const cv = canvasRef.current
    if (!cv || !ls || notes.length === 0) return
    const ctx = cv.getContext('2d')
    if (!ctx) return
    const w = cv.width
    const h = cv.height
    ctx.fillStyle = '#141414'
    ctx.fillRect(0, 0, w, h)
    const midis = notes.map((n, i) => editedMidi(i, n.midi))
    const lo = Math.min(...midis) - 2
    const hi = Math.max(...midis) + 2
    const totalBeats = ls.stats.bar_count * ls.meta.beats_per_bar || 1
    const pcs = scalePitchClasses(ls.meta.key)
    // 调内音阶线
    for (let m = lo; m <= hi; m++) {
      const y = h - ((m - lo) / (hi - lo)) * h
      ctx.strokeStyle = pcs.has(((m % 12) + 12) % 12) ? 'rgba(63,220,122,.10)' : 'rgba(255,255,255,.03)'
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(w, y)
      ctx.stroke()
    }
    // 小节线
    for (let b = 0; b <= ls.stats.bar_count; b++) {
      const x = (b * ls.meta.beats_per_bar / totalBeats) * w
      ctx.strokeStyle = 'rgba(255,255,255,.10)'
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, h)
      ctx.stroke()
    }
    // 音符（编辑过的用强调色；选中描边）
    let cursor = 0
    ls.bars.forEach((bar) => {
      bar.notes.forEach((n) => {
        const i = cursor++
        const midi = editedMidi(i, n.midi)
        const x0 = (n.beat / totalBeats) * w
        const x1 = ((n.beat + n.dur) / totalBeats) * w
        const y = h - ((midi - lo + 0.5) / (hi - lo + 1)) * h
        const edited = (edits[i] ?? 0) !== 0
        ctx.fillStyle = i === selected ? '#ffffff' : edited ? '#ffb454' : '#3fdc7a'
        ctx.fillRect(x0, y - 3, Math.max(3, x1 - x0 - 1), 6)
        if (n.syllable && x1 - x0 > 14) {
          ctx.fillStyle = 'rgba(255,255,255,.55)'
          ctx.font = '9px sans-serif'
          ctx.fillText(n.syllable, x0 + 1, y - 5)
        }
      })
    })
  }, [ls, notes, edits, selected, editedMidi])

  const onCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const cv = e.currentTarget
    const rect = cv.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * cv.width
    const y = ((e.clientY - rect.top) / rect.height) * cv.height
    // 最近音符命中（时间窗优先）
    if (!ls) return
    const totalBeats = ls.stats.bar_count * ls.meta.beats_per_bar || 1
    const beat = (x / cv.width) * totalBeats
    let best: number | null = null
    let bestDist = Infinity
    let cursor = 0
    ls.bars.forEach((bar) => {
      bar.notes.forEach((n) => {
        const i = cursor++
        const d = Math.abs(n.beat + n.dur / 2 - beat)
        if (d < bestDist) {
          bestDist = d
          best = i
        }
      })
    })
    void y
    if (best !== null && bestDist <= ls.meta.beats_per_bar) setSelected(best)
  }

  const submit = async () => {
    if (!candidate || submitting) return
    const items = Object.entries(edits).filter(([, semi]) => semi !== 0)
    if (items.length === 0 && quantize === 'off') {
      toast(t('pitch.toast.noEdits'), 'warn')
      return
    }
    if (items.length === 0) {
      toast(t('pitch.toast.quantizeOnly'))
    }
    setSubmitting(true)
    try {
      const payload = items.map(([i, semi]) => ({
        beat: Number(Number(notes[Number(i)].beat).toFixed(3)),
        semi,
      }))
      const res = await pitchEditCandidate(candidate.id, { edits: payload, quantize })
      // 轮询到终态（确定性渲染秒级完成）
      for (let k = 0; k < 60; k++) {
        await new Promise((r) => setTimeout(r, 1000))
        const task = await getTask(res.task.id)
        if (task.status === 'succeeded') {
          toast(t('pitch.toast.done', { no: k + 1 }))
          setEdits({})
          if (task.version_id) void loadVersion(task.version_id)
          break
        }
        if (task.status === 'failed') {
          toast(task.error?.message ?? t('pitch.toast.failed'), 'bad')
          break
        }
      }
    } catch {
      /* 拦截器已 toast */
    } finally {
      setSubmitting(false)
    }
  }

  const editCount = Object.values(edits).filter((v) => v !== 0).length

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4">
        <div className="label">{t('pitch.view.label')}</div>
        <h1 className="text-[28px] font-extrabold tracking-tight mt-1">{t('pitch.view.headline')}</h1>
      </header>

      <div className="px-8 flex gap-2 flex-wrap items-center">
        <select className="!text-[11px] max-w-52" value={workId} onChange={(e) => setWorkId(e.target.value)}>
          <option value="">{t('pitch.pick.work')}</option>
          {works.map((w) => (
            <option key={w.id} value={w.id}>{w.display_code} · {w.title}</option>
          ))}
        </select>
        {ls && (
          <span className="text-[10px] num" style={{ color: 'var(--dim)' }}>
            {ls.meta.key} · {ls.meta.bpm} BPM · {ls.stats.note_count} notes
          </span>
        )}
      </div>

      <div className="px-8 mt-3 flex gap-1.5 flex-wrap items-center">
        <button className="btn btn-ghost !py-1 !px-2.5 text-[10px]" onClick={snapToScale} disabled={!ls}>
          {t('pitch.snapScale')}
        </button>
        <select className="!text-[10px]" value={quantize} onChange={(e) => setQuantize(e.target.value as 'off' | '8' | '16')}>
          <option value="off">{t('pitch.quantize.off')}</option>
          <option value="8">{t('pitch.quantize.8')}</option>
          <option value="16">{t('pitch.quantize.16')}</option>
        </select>
        <span className="text-[10px] ml-2" style={{ color: 'var(--dim)' }}>
          {selected !== null && notes[selected]
            ? t('pitch.selected', {
                name: midiName(editedMidi(selected, notes[selected].midi)),
                s: edits[selected] ?? 0,
              })
            : t('pitch.hint.select')}
        </span>
      </div>

      <div className="rule-t flex-1 min-h-0 px-8 py-5 overflow-y-auto">
        {!ls && (
          <div className="border border-dashed py-16 text-center text-[12px]" style={{ borderColor: 'var(--line)', color: 'var(--dim)' }}>
            {t('pitch.empty')}
          </div>
        )}
        {ls && notes.length === 0 && (
          <div className="border border-dashed py-16 text-center text-[12px]" style={{ borderColor: 'var(--line)', color: 'var(--dim)' }}>
            {t('pitch.empty.notes')}
          </div>
        )}
        {notes.length > 0 && (
          <canvas
            ref={canvasRef}
            width={1200}
            height={320}
            className="w-full"
            style={{ background: '#141414', cursor: 'pointer', borderRadius: 6 }}
            onClick={onCanvasClick}
            data-testid="pitch-roll"
          />
        )}
        {notes.length > 0 && (
          <div className="flex items-center gap-3 mt-4">
            <button
              className="btn btn-acc !py-1.5 !px-4 text-[12px]"
              disabled={submitting || (editCount === 0 && quantize === 'off')}
              onClick={() => void submit()}
            >
              {submitting ? t('pitch.submitting') : t('pitch.submit', { n: editCount })}
            </button>
            <span className="text-[10px]" style={{ color: 'var(--dim)' }}>{t('pitch.submit.hint')}</span>
          </div>
        )}
      </div>
      <p className="px-8 pb-3 text-[10px]" style={{ color: 'var(--dim)' }}>{t('pitch.footnote')}</p>
    </section>
  )
}
