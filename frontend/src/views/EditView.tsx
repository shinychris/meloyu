import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FileRef, Work } from '../types/api'
import { listWorks, getVersionTree } from '../api/works'
import { listCandidates } from '../api/generation'
import { getStreamToken } from '../api/files'
import { apiPost } from '../api/client'
import { encodeWav } from '../lib/mixer'
import {
  detectClips, detectSilence, peaksOf, renderEdit, toAudioBuffer,
  type EditOp, nextOpId,
} from '../lib/audioedit'
import { toast } from '../stores/toast'
import { useT, t as tGlobal } from '../i18n'
import { formatDuration } from '../lib/format'

type Tool = 'cut' | 'keep' | 'fadein' | 'fadeout' | 'gainUp' | 'gainDown' | 'normalize'

interface VersionLite {
  id: string
  version_no: string
}

/**
 * 音频剪辑（/edit，v0.11.0）：波形选区 + 剪掉/保留/淡入淡出/增益/标准化 +
 * 爆音与静音检测 + 撤销/重做（非破坏：每次从原始母带重放操作），
 * 成品经 OfflineAudioContext 口径离线渲染为 48k wav → POST /versions/{id}/mixdown
 * 存为新版本（人类参与留痕，与 /arrange 同一回存通道）。
 */
export default function EditView() {
  const t = useT()
  const [works, setWorks] = useState<Work[]>([])
  const [workId, setWorkId] = useState<string>('')
  const [nodes, setNodes] = useState<VersionLite[]>([])
  const [versionId, setVersionId] = useState<string>('')
  const [buffer, setBuffer] = useState<AudioBuffer | null>(null)
  const [loading, setLoading] = useState(false)
  // 撤销/重做合并为单一 state（P1-19）：在 setState updater 内嵌套另一个
  // setState 是 React 禁止的副作用——StrictMode 双调 updater 会把 redoStack
  // 推入重复快照（redo 一次跳两级），并发重放同样危险
  const [hist, setHist] = useState<{ ops: EditOp[]; redo: EditOp[][] }>({ ops: [], redo: [] })
  const ops = hist.ops
  const redoStack = hist.redo
  const [tool, setTool] = useState<Tool>('cut')
  const [sel, setSel] = useState<{ a: number; b: number } | null>(null)
  const [playing, setPlaying] = useState(false)
  const [saving, setSaving] = useState(false)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const audioElRef = useRef<HTMLAudioElement | null>(null)
  const previewUrlRef = useRef<string | null>(null)

  useEffect(() => {
    listWorks({ page_size: 100 }).then((r) => setWorks(r.items)).catch(() => {})
  }, [])

  useEffect(() => {
    if (!workId) return
    getVersionTree(workId)
      .then((tree: { nodes: Array<{ id: string; version_no: string }>; current_version_id: string | null }) => {
        setNodes(tree.nodes.map((n) => ({ id: n.id, version_no: n.version_no })))
        setVersionId(tree.current_version_id ?? '')
      })
      .catch(() => setNodes([]))
  }, [workId])

  const loadVersion = useCallback(async (vid: string) => {
    setLoading(true)
    setBuffer(null)
    setHist({ ops: [], redo: [] })
    setSel(null)
    try {
      const res = await listCandidates(vid)
      const cand = res.items.find((c) => c.adopted) ?? res.items[0]
      if (!cand) return
      const master = cand.files.find((f) => f.kind === 'master')
      const preview = cand.files.find((f) => f.kind === 'preview')
      const file: FileRef | undefined = master ?? preview
      if (!file) {
        // 用模块级 t（非响应式）：不让 locale 变化重建本回调——否则切语言会
        // 重放整个加载流程（重新拉 stream-token + fetch 整曲 + decodeAudioData），
        // 编辑中的 ops/选区全被清空（P1-20）
        toast(tGlobal('edit.toast.noAudio'), 'warn')
        return
      }
      const { url } = await getStreamToken(file.file_id)
      const raw = await fetch(url).then((r) => r.arrayBuffer())
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      const tmp = new Ctx()
      const buf = await tmp.decodeAudioData(raw)
      void tmp.close()
      setBuffer(buf)
    } catch {
      /* 拦截器已 toast */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (versionId) void loadVersion(versionId)
  }, [versionId, loadVersion])

  // 渲染结果（操作全量重放）
  const rendered = useMemo(() => (buffer ? renderEdit(buffer, ops) : null), [buffer, ops])
  const renderDuration = rendered?.duration ?? 0
  const clipInfo = useMemo(() => (buffer ? detectClips(buffer) : null), [buffer])
  const silenceRatio = useMemo(() => (buffer ? detectSilence(buffer) : 0), [buffer])
  const saveBlocked = renderDuration < 30 || renderDuration > 240

  // 波形绘制（渲染结果）
  useEffect(() => {
    const cv = canvasRef.current
    if (!cv || !rendered) return
    const ctx = cv.getContext('2d')
    if (!ctx) return
    const w = cv.width
    const h = cv.height
    ctx.fillStyle = '#141414'
    ctx.fillRect(0, 0, w, h)
    const peaks = peaksOf(toAudioBuffer(rendered), w)
    const mid = h / 2
    ctx.strokeStyle = '#3fdc7a'
    ctx.beginPath()
    for (let x = 0; x < w; x++) {
      const p = peaks[x] ?? 0
      ctx.moveTo(x + 0.5, mid - (p * mid * 0.92))
      ctx.lineTo(x + 0.5, mid + (p * mid * 0.92))
    }
    ctx.stroke()
    // 选区
    if (sel && renderDuration > 0) {
      const x0 = Math.floor((sel.a / renderDuration) * w)
      const x1 = Math.ceil((sel.b / renderDuration) * w)
      ctx.fillStyle = 'rgba(63,220,122,.14)'
      ctx.fillRect(x0, 0, Math.max(2, x1 - x0), h)
      ctx.strokeStyle = 'rgba(63,220,122,.8)'
      ctx.beginPath()
      ctx.moveTo(x0 + 0.5, 0); ctx.lineTo(x0 + 0.5, h)
      ctx.moveTo(x1 + 0.5, 0); ctx.lineTo(x1 + 0.5, h)
      ctx.stroke()
    }
  }, [rendered, sel, renderDuration])

  // 选区拖拽
  const onCanvasMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!renderDuration) return
    const rect = e.currentTarget.getBoundingClientRect()
    const toSec = (x: number) =>
      Math.max(0, Math.min(renderDuration, ((x - rect.left) / rect.width) * renderDuration))
    const a = toSec(e.clientX)
    const move = (ev: MouseEvent) => {
      const target = document.elementFromPoint(ev.clientX, ev.clientY)
      if (!target) return
      const r = (target as HTMLElement).getBoundingClientRect
        ? (target as HTMLElement).getBoundingClientRect()
        : rect
      setSel({ a, b: toSec(ev.clientX) })
      void r
    }
    const up = () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
    }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
    setSel({ a, b: a })
  }

  const pushOp = (op: EditOp) => {
    setHist((h) => ({ ops: [...h.ops, op], redo: [...h.redo, h.ops] }))
  }

  const applyTool = () => {
    if (!sel || sel.b - sel.a < 0.01) {
      toast(t('edit.toast.needSelection'), 'warn')
      return
    }
    const start = Math.min(sel.a, sel.b)
    const end = Math.max(sel.a, sel.b)
    const map: Record<Tool, EditOp['type'] | null> = {
      cut: 'cut', keep: 'keep', fadein: 'fadein', fadeout: 'fadeout',
      gainUp: 'gain', gainDown: 'gain', normalize: 'normalize',
    }
    const type = map[tool]
    if (!type) return
    pushOp({
      id: nextOpId(), type, start, end,
      db: tool === 'gainUp' ? 3 : tool === 'gainDown' ? -3 : undefined,
      target: type === 'normalize' ? 0.99 : undefined,
    })
    toast(t('edit.toast.opApplied', { n: ops.length + 1 }))
  }

  const undo = () => {
    setHist((h) => h.ops.length === 0 ? h : {
      ops: h.ops.slice(0, -1),
      redo: [...h.redo, h.ops],
    })
  }
  const redo = () => {
    setHist((h) => h.redo.length === 0 ? h : {
      ops: h.redo[h.redo.length - 1],
      redo: h.redo.slice(0, -1),
    })
  }

  // 预览播放（渲染结果 → blob URL）
  const playPreview = () => {
    if (!rendered) return
    if (playing) {
      audioElRef.current?.pause()
      setPlaying(false)
      return
    }
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current)
    const buf = toAudioBuffer(rendered)
    const wav = encodeWav(buf)
    const url = URL.createObjectURL(new Blob([wav], { type: 'audio/wav' }))
    previewUrlRef.current = url
    const el = audioElRef.current ?? new Audio()
    audioElRef.current = el
    el.src = url
    el.onended = () => setPlaying(false)
    void el.play()
    setPlaying(true)
  }

  useEffect(() => () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current)
  }, [])

  const save = async () => {
    if (!rendered || !versionId || saving || saveBlocked) return
    setSaving(true)
    try {
      const buf = toAudioBuffer(rendered)
      const wav = encodeWav(buf)
      const res = await apiPost<{ version: { version_no: string } }>(
        `/versions/${versionId}/mixdown`,
        wav,
        { headers: { 'Content-Type': 'application/octet-stream' },
          params: { notes: t('edit.save.notes', { n: ops.length }) } },
      )
      toast(t('edit.toast.saved', { no: res.version.version_no }))
      setHist({ ops: [], redo: [] })
    } catch {
      /* 拦截器已 toast（时长守卫等） */
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4">
        <div className="label">{t('edit.view.label')}</div>
        <h1 className="text-[28px] font-extrabold tracking-tight mt-1">{t('edit.view.headline')}</h1>
      </header>

      <div className="px-8 flex gap-2 flex-wrap items-center">
        <select className="!text-[11px] max-w-52" value={workId} onChange={(e) => setWorkId(e.target.value)}>
          <option value="">{t('edit.pick.work')}</option>
          {works.map((w) => (
            <option key={w.id} value={w.id}>{w.display_code} · {w.title}</option>
          ))}
        </select>
        <select className="!text-[11px]" value={versionId} onChange={(e) => setVersionId(e.target.value)} disabled={!nodes.length}>
          <option value="">{t('edit.pick.version')}</option>
          {nodes.map((n) => (
            <option key={n.id} value={n.id}>{n.version_no}</option>
          ))}
        </select>
        <span className="text-[10px] num ml-1" style={{ color: 'var(--dim)' }}>
          {renderDuration > 0 && `${formatDuration(renderDuration)} · ${ops.length} ops`}
        </span>
      </div>

      <div className="px-8 mt-3 flex gap-1.5 flex-wrap">
        {(['cut', 'keep', 'fadein', 'fadeout', 'gainUp', 'gainDown', 'normalize'] as Tool[]).map((k) => (
          <button type="button" key={k} className={`chip ${tool === k ? 'on' : ''}`} onClick={() => setTool(k)}>
            {t(`edit.tool.${k}` as never)}
          </button>
        ))}
      </div>

      <div className="px-8 mt-3 flex gap-2 flex-wrap items-center">
        <button className="btn btn-acc !py-1.5 !px-3 text-[11px]" disabled={!sel} onClick={applyTool}>
          {t('edit.apply')}
        </button>
        <button className="btn btn-ghost !py-1.5 !px-3 text-[11px]" disabled={!ops.length} onClick={undo}>
          ↩ {t('edit.undo')}
        </button>
        <button className="btn btn-ghost !py-1.5 !px-3 text-[11px]" disabled={!redoStack.length} onClick={redo}>
          ↪ {t('edit.redo')}
        </button>
        <button className="btn btn-ghost !py-1.5 !px-3 text-[11px]" disabled={!rendered} onClick={playPreview}>
          {playing ? '⏸' : '▶'} {t('edit.preview')}
        </button>
        <span className="text-[10px] ml-auto num" style={{ color: 'var(--dim)' }}>
          {clipInfo && clipInfo.count > 0 && t('edit.info.clips', { n: clipInfo.count })}
          {clipInfo && clipInfo.count === 0 && t('edit.info.clean')}
          {silenceRatio > 0.05 && ` · ${t('edit.info.silence', { pct: Math.round(silenceRatio * 100) })}`}
        </span>
      </div>

      <div className="rule-t flex-1 min-h-0 px-8 py-5 overflow-y-auto">
        {!buffer && (
          <div className="border border-dashed py-16 text-center text-[12px]" style={{ borderColor: 'var(--line)', color: 'var(--dim)' }}>
            {loading ? t('edit.loading') : t('edit.empty')}
          </div>
        )}
        {buffer && (
          <>
            <canvas
              ref={canvasRef}
              width={1200}
              height={180}
              className="w-full"
              style={{ background: '#141414', cursor: 'crosshair', borderRadius: 6 }}
              onMouseDown={onCanvasMouseDown}
              data-testid="edit-waveform"
            />
            <div className="flex items-center gap-3 mt-4">
              <button className="btn btn-acc !py-1.5 !px-4 text-[12px]" disabled={!ops.length || saving || saveBlocked} onClick={() => void save()}>
                {saving ? t('edit.saving') : t('edit.save')}
              </button>
              {saveBlocked && ops.length > 0 && (
                <span className="text-[10px]" style={{ color: 'var(--bad)' }}>
                  {t('edit.save.rangeWarn', { s: formatDuration(renderDuration) })}
                </span>
              )}
              <span className="text-[10px]" style={{ color: 'var(--dim)' }}>{t('edit.save.hint')}</span>
            </div>
            {ops.length > 0 && (
              <div className="card p-3 mt-4">
                <div className="label mb-2">{t('edit.ops.title')}</div>
                <div className="flex gap-1.5 flex-wrap">
                  {ops.map((op) => (
                    <span key={op.id} className="text-[9px] px-1.5 py-0.5" style={{ background: 'var(--bg3)', color: 'var(--muted)' }}>
                      {t(`edit.tool.${op.type === 'gain' ? (op.db && op.db > 0 ? 'gainUp' : 'gainDown') : op.type}` as never)}
                      {' '}{op.start.toFixed(1)}–{op.end.toFixed(1)}s
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
      <p className="px-8 pb-3 text-[10px]" style={{ color: 'var(--dim)' }}>{t('edit.footnote')}</p>
    </section>
  )
}
