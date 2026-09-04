import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Candidate, FileRef, Work } from '../types/api'
import { listWorks } from '../api/works'
import { getVersionTree } from '../api/works'
import type { VersionTreeNode } from '../types/api'
import { listCandidates } from '../api/generation'
import { getTask } from '../api/generation'
import { getStreamToken } from '../api/files'
import { apiPost } from '../api/client'
import { DEFAULT_PARAMS, Mixer, peaksOf, type TrackParams } from '../lib/mixer'
import { toast } from '../stores/toast'
import { useT } from '../i18n'
import { formatDuration } from '../lib/format'

const STEM_NAMES = ['vocals', 'drums', 'bass', 'other'] as const
const EQ_KEYS = { low: 'editor.eq.low', mid: 'editor.eq.mid', high: 'editor.eq.high' } as const
const STEM_LABEL_KEYS: Record<string, 'editor.stem.vocals' | 'editor.stem.drums' | 'editor.stem.bass' | 'editor.stem.other'> = {
  vocals: 'editor.stem.vocals',
  drums: 'editor.stem.drums',
  bass: 'editor.stem.bass',
  other: 'editor.stem.other',
}

interface Lane {
  file: FileRef
  peaks: number[]
  params: TrackParams
}

/**
 * 多轨编辑器（V2，v0.9.0）：本地引擎分轨（vocals/drums/bass/other）时间线 +
 * 每轨音量/mute/solo + 3 段 EQ（Web Audio）+ 变速变调（retune 服务端确定性重渲染）+
 * 混音回存（OfflineAudioContext 渲染 → mixdown 子版本，人类参与留痕）。
 */
export default function ArrangementView() {
  const t = useT()
  const navigate = useNavigate()
  const [works, setWorks] = useState<Work[]>([])
  const [workId, setWorkId] = useState<string | null>(null)
  const [nodes, setNodes] = useState<VersionTreeNode[]>([])
  const [currentVersionId, setCurrentVersionId] = useState<string | null>(null)
  const [versionId, setVersionId] = useState<string | null>(null)
  const [candidate, setCandidates] = useState<Candidate | null>(null)
  const [lanes, setLanes] = useState<Lane[]>([])
  const [loading, setLoading] = useState(false)
  const [position, setPosition] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [saving, setSaving] = useState(false)
  const [retuning, setRetuning] = useState(false)
  const [retuneBpm, setRetuneBpm] = useState(96)
  const mixerRef = useRef<Mixer | null>(null)
  const rafRef = useRef<number>(0)
  /** 装载累积：loadVersion 解码出的 AudioBuffer 轨（Mixer 构建输入） */
  const tracksRef = useRef<{ name: string; buffer: AudioBuffer; params: TrackParams }[]>([])

  useEffect(() => {
    listWorks({ page_size: 50 })
      .then((r) => setWorks(r.items.filter((w) => (w.exported_formats ?? []).length >= 0)))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!workId) return
    getVersionTree(workId)
      .then((tree) => {
        setNodes(tree.nodes)
        setCurrentVersionId(tree.current_version_id)
        setVersionId(tree.current_version_id)
      })
      .catch(() => setNodes([]))
  }, [workId])

  const loadVersion = useCallback(async (vid: string) => {
    setLoading(true)
    setLanes([])
    tracksRef.current = []
    try {
      const res = await listCandidates(vid)
      const cand = res.items.find((c) => c.adopted) ?? res.items[0]
      setCandidates(cand ?? null)
      if (!cand) return
      const stems = STEM_NAMES.map((n) => cand.files.find((f) => f.kind === 'stem' && f.stem_name === n)).filter(Boolean) as FileRef[]
      if (stems.length === 0) {
        toast(t('editor.toast.noStems'), 'warn')
        return
      }
      const loaded: Lane[] = []
      for (const f of stems) {
        const { url } = await getStreamToken(f.file_id)
        const raw = await fetch(url).then((r) => r.arrayBuffer())
        const Ctx =
          window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
        const tmp = new Ctx()
        const buf = await tmp.decodeAudioData(raw)
        void tmp.close()
        loaded.push({ file: f, peaks: peaksOf(buf), params: { ...DEFAULT_PARAMS } })
        tracksRef.current.push({ name: f.stem_name ?? 'x', buffer: buf, params: { ...DEFAULT_PARAMS } })
      }
      setLanes(loaded)
    } catch {
      /* 拦截器已 toast */
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t])

  useEffect(() => {
    if (versionId) void loadVersion(versionId)
  }, [versionId, loadVersion])

  // 播放器实例：lanes 就绪后创建
  useEffect(() => {
    mixerRef.current?.close()
    if (tracksRef.current.length === 0) {
      mixerRef.current = null
      return
    }
    const m = new Mixer()
    m.load(tracksRef.current)
    mixerRef.current = m
    return () => {
      m.close()
      mixerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lanes])

  // 时间轴 rAF
  useEffect(() => {
    const tick = () => {
      const m = mixerRef.current
      if (m) {
        setPosition(m.currentTime)
        setPlaying(m.playing)
        if (m.playing && m.currentTime >= m.duration - 0.05) {
          m.pause()
          m.seek(0)
        }
      }
      rafRef.current = window.requestAnimationFrame(tick)
    }
    rafRef.current = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(rafRef.current)
  }, [])

  const duration = lanes.length ? mixerRef.current?.duration ?? 0 : 0

  const setLaneParams = (i: number, patch: Partial<TrackParams>) => {
    setLanes((prev) => {
      const next = prev.map((l, j) => (j === i ? { ...l, params: { ...l.params, ...patch } } : l))
      mixerRef.current?.setParams(i, next[i].params)
      return next
    })
  }

  const setEq = (i: number, band: 'low' | 'mid' | 'high', v: number) => {
    setLanes((prev) => {
      const next = prev.map((l, j) => (j === i ? { ...l, params: { ...l.params, eq: { ...l.params.eq, [band]: v } } } : l))
      mixerRef.current?.setParams(i, next[i].params)
      return next
    })
  }

  const onPlay = async () => {
    const m = mixerRef.current
    if (!m) return
    if (m.playing) m.pause()
    else await m.play()
  }

  const saveMixdown = async () => {
    const m = mixerRef.current
    if (!m || saving) return
    setSaving(true)
    try {
      const wav = await m.buildForRender()
      const res = await apiPost<{ version: { id: string; version_no: string }; work: { id: string; title: string } }>(
        `/versions/${versionId}/mixdown`,
        wav,
        {
          params: { notes: t('editor.mixdown.notes') },
          headers: { 'Content-Type': 'application/octet-stream' },
          timeout: 120000,
        },
      )
      toast(t('editor.toast.mixdownSaved', { no: res.version.version_no }))
      navigate(`/works/${res.work.id}`)
    } catch {
      setSaving(false)
    } finally {
      setSaving(false)
    }
  }

  const doRetune = async () => {
    if (!candidate || retuning) return
    if (retuneBpm === candidate.bpm) {
      toast(t('editor.toast.sameBpm'), 'warn')
      return
    }
    setRetuning(true)
    try {
      const { task } = await apiPost<{ task: { id: string } }>(`/candidates/${candidate.id}/retune`, {
        bpm: retuneBpm,
      })
      for (let i = 0; i < 200; i++) {
        const tk = await getTask(task.id)
        if (tk.status === 'succeeded') {
          toast(t('editor.toast.retuneDone', { bpm: retuneBpm }))
          setRetuning(false)
          if (workId) {
            const tree = await getVersionTree(workId)
            setNodes(tree.nodes)
            setCurrentVersionId(tree.current_version_id)
            setVersionId(tree.current_version_id)
          }
          return
        }
        if (tk.status === 'failed' || tk.status === 'canceled') {
          toast(tk.error?.message ?? t('editor.toast.retuneFailed'), 'bad')
          break
        }
        await new Promise((r) => window.setTimeout(r, 1500))
      }
    } catch {
      /* 拦截器已 toast */
    } finally {
      setRetuning(false)
    }
  }

  const stemLabel = (s: string | null) => (s && STEM_LABEL_KEYS[s] ? t(STEM_LABEL_KEYS[s]) : s ?? '')

  const timelinePct = duration > 0 ? Math.min(100, (position / duration) * 100) : 0
  const workOptions = useMemo(() => works, [works])

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4">
        <div className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <div className="label">{t('editor.view.label')}</div>
            <h1 className="text-[28px] font-extrabold tracking-tight mt-1">{t('editor.view.headline')}</h1>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={workId ?? ''}
              onChange={(e) => setWorkId(e.target.value || null)}
              className="!text-[12px]"
            >
              <option value="">{t('editor.pick.work')}</option>
              {workOptions.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.display_code} · {w.title}
                </option>
              ))}
            </select>
            <select
              value={versionId ?? ''}
              onChange={(e) => setVersionId(e.target.value || null)}
              className="!text-[12px]"
              disabled={!workId}
            >
              <option value="">{t('editor.pick.version')}</option>
              {nodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.version_no} · {n.source}{n.id === currentVersionId ? ' ✓' : ''}
                </option>
              ))}
            </select>
          </div>
        </div>
      </header>

      {!workId || !versionId ? (
        <div className="flex-1 grid place-items-center">
          <div className="text-center">
            <div className="text-[13px]" style={{ color: 'var(--muted)' }}>{t('editor.empty.title')}</div>
            <div className="text-[11px] mt-2" style={{ color: 'var(--dim)' }}>{t('editor.empty.hint')}</div>
          </div>
        </div>
      ) : loading ? (
        <div className="flex-1 grid place-items-center text-[12px]" style={{ color: 'var(--dim)' }}>
          {t('editor.loading')}
        </div>
      ) : lanes.length === 0 ? (
        <div className="flex-1 grid place-items-center text-[12px]" style={{ color: 'var(--dim)' }}>
          {t('editor.toast.noStems')}
        </div>
      ) : (
        <div className="rule-t flex-1 min-h-0 flex flex-col">
          {/* 传输条 */}
          <div className="px-8 py-3 flex items-center gap-4" style={{ borderBottom: '1px solid var(--line)' }}>
            <button className="btn btn-acc !py-1.5 !px-4 text-[12px]" onClick={() => void onPlay()}>
              {playing ? '⏸' : '▶'} {playing ? t('editor.transport.pause') : t('editor.transport.play')}
            </button>
            <span className="num text-[11px]" style={{ color: 'var(--muted)' }}>
              {formatDuration(position)} / {formatDuration(duration)}
            </span>
            <div
              className="flex-1 h-6 cursor-pointer relative"
              style={{ background: 'var(--bg2)' }}
              onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect()
                const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
                mixerRef.current?.seek(pct * duration)
                setPosition(pct * duration)
              }}
              data-testid="editor-timeline"
            >
              <div
                className="absolute inset-y-0 left-0"
                style={{ width: `${timelinePct}%`, background: 'var(--acc-dim)' }}
              />
              <div
                className="absolute inset-y-0 w-[2px]"
                style={{ left: `${timelinePct}%`, background: 'var(--acc)' }}
              />
            </div>
            <button className="btn btn-ghost !py-1.5 !px-3 text-[11px]" onClick={() => mixerRef.current?.seek(0)}>
              ⏮ {t('editor.transport.rewind')}
            </button>
          </div>

          {/* 轨道 */}
          <div className="flex-1 overflow-y-auto px-8 py-4 space-y-3">
            {lanes.map((lane, i) => (
              <div key={lane.file.file_id} className="card p-3" data-testid={`editor-lane-${lane.file.stem_name}`}>
                <div className="flex items-center gap-3">
                  <div className="w-20 text-[12px] font-bold">{stemLabel(lane.file.stem_name)}</div>
                  <canvas
                    className="flex-1 h-14"
                    style={{ background: 'var(--bg2)' }}
                    ref={(el) => {
                      if (!el) return
                      const w = (el.width = el.clientWidth || 600)
                      const h = (el.height = el.clientHeight || 56)
                      const ctx = el.getContext('2d')
                      if (!ctx) return
                      ctx.clearRect(0, 0, w, h)
                      ctx.fillStyle = '#00ff2c'
                      lane.peaks.forEach((p, x) => {
                        const bw = w / lane.peaks.length
                        const hh = Math.max(1, p * h * 0.9)
                        ctx.fillRect(x * bw, (h - hh) / 2, Math.max(1, bw - 0.5), hh)
                      })
                    }}
                  />
                  <button
                    className={`btn !py-1 !px-2 text-[10px] ${lane.params.muted ? 'btn-acc' : 'btn-ghost'}`}
                    onClick={() => setLaneParams(i, { muted: !lane.params.muted })}
                  >
                    M
                  </button>
                  <button
                    className={`btn !py-1 !px-2 text-[10px] ${lane.params.solo ? 'btn-acc' : 'btn-ghost'}`}
                    onClick={() => setLaneParams(i, { solo: !lane.params.solo })}
                  >
                    S
                  </button>
                </div>
                <div className="flex items-center gap-4 mt-2 flex-wrap">
                  <label className="flex items-center gap-1.5 text-[10px]" style={{ color: 'var(--dim)' }}>
                    {t('editor.track.volume')}
                    <input
                      type="range"
                      min={0}
                      max={1.4}
                      step={0.05}
                      value={lane.params.volume}
                      onChange={(e) => setLaneParams(i, { volume: Number(e.target.value) })}
                    />
                    <span className="num">{Math.round(lane.params.volume * 100)}%</span>
                  </label>
                  {(['low', 'mid', 'high'] as const).map((band) => (
                    <label key={band} className="flex items-center gap-1.5 text-[10px]" style={{ color: 'var(--dim)' }}>
                      {t(EQ_KEYS[band])}
                      <input
                        type="range"
                        min={-12}
                        max={12}
                        step={0.5}
                        value={lane.params.eq[band]}
                        onChange={(e) => setEq(i, band, Number(e.target.value))}
                      />
                      <span className="num">{lane.params.eq[band] > 0 ? '+' : ''}{lane.params.eq[band]}dB</span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* 底部操作：变速变调 + 混音回存 */}
          <div className="px-8 py-4 flex items-center gap-3 flex-wrap rule-t">
            <span className="label">{t('editor.retune.title')}</span>
            <input
              type="number"
              min={60}
              max={174}
              value={retuneBpm}
              onChange={(e) => setRetuneBpm(Number(e.target.value))}
              className="!text-[12px] w-20 num"
            />
            <span className="text-[11px]" style={{ color: 'var(--dim)' }}>BPM</span>
            <button className="btn btn-ghost !py-1.5 !px-3 text-[11px]" disabled={retuning} onClick={() => void doRetune()}>
              {retuning ? t('editor.retune.running') : t('editor.retune.run')}
            </button>
            <div className="flex-1" />
            <button className="btn btn-acc !py-2 !px-4 text-[12px] font-bold" disabled={saving} onClick={() => void saveMixdown()}>
              {saving ? t('editor.mixdown.saving') : t('editor.mixdown.save')}
            </button>
          </div>
          <div className="px-8 pb-3 text-[9px] leading-relaxed" style={{ color: 'var(--dim)' }}>
            {t('editor.footnote')}
          </div>
        </div>
      )}
    </section>
  )
}
