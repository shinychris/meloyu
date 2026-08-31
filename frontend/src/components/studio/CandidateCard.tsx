import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Candidate, GenerationSubmitResult, RegenSectionRequest } from '../../types/api'
import { drawWave } from '../../lib/wave'
import { formatDuration, keyLabel, VOCAL_LABEL } from '../../lib/format'
import { usePlayerStore } from '../../stores/player'
import { useStudioStore } from '../../stores/studio'
import { toast } from '../../stores/toast'
import {
  adoptCandidate,
  extendCandidate,
  regenSectionCandidate,
  variantCandidate,
} from '../../api/generation'
import { SECTION_LABEL } from '../../lib/format'
import DerivePanel, { type DeriveKind } from './DerivePanel'

/** 候选卡：封面波形 + AI 质量分 + 标签 + 时长 + 结构段条 + 操作按钮 */
export default function CandidateCard({
  candidate,
  index,
  workTitle,
  modelLabel,
}: {
  candidate: Candidate
  index: number
  workTitle: string
  modelLabel: string
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const navigate = useNavigate()
  const playTrack = usePlayerStore((s) => s.playTrack)
  const workId = useStudioStore((s) => s.workId)
  /** 生成中（含延长/变体/段落重生成等派生任务）：禁用派生操作，避免并发扣积分 */
  const generating =
    useStudioStore((s) => s.submitting) ||
    useStudioStore((s) => s.task != null && (s.task.status === 'queued' || s.task.status === 'running'))
  /** V1.1 派生操作面板：extend 选秒数 / variant 输入风格 / regen 选段落 */
  const [panel, setPanel] = useState<DeriveKind | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (canvasRef.current) drawWave(canvasRef.current, candidate.seed, '#00ff2c')
  }, [candidate.seed])

  const previewFile = candidate.files.find((f) => f.kind === 'preview')
  const title = `${workTitle} · 候选 ${candidate.label}`
  const subtitle = `${modelLabel} · ${candidate.bpm} BPM · ${keyLabel(candidate.key)}`

  const onPlay = () => {
    if (!previewFile) {
      toast('该候选暂无预览音频', 'warn')
      return
    }
    void playTrack({
      fileId: previewFile.file_id,
      title,
      subtitle,
      durationSec: candidate.duration_sec,
    })
    useStudioStore.getState().logOp(`试听：${title}`)
  }

  const onAdopt = async () => {
    try {
      await adoptCandidate(candidate.id)
      const s = useStudioStore.getState()
      useStudioStore.setState({
        candidates: s.candidates.map((c) => ({ ...c, adopted: c.id === candidate.id })),
      })
      s.logOp(`采用候选 ${candidate.label}（定稿）`)
      s.refreshVersionTree()
      toast(`已采用候选 ${candidate.label} 为当前版本`)
    } catch {
      /* 40901 重复采用等已 toast */
    }
  }

  /** 派生操作统一入口：提交成功交给 store 接管轮询；失败（含后端未升级的 501）由拦截器 toast */
  const runDerived = async (op: () => Promise<GenerationSubmitResult>, label: string) => {
    setBusy(true)
    try {
      const result = await op()
      useStudioStore.getState().startDerivedGeneration(result, `${label} · 候选 ${candidate.label}`)
      setPanel(null)
    } catch {
      /* 拦截器已 toast（50101 功能未上线 / 40201 积分不足等） */
    } finally {
      setBusy(false)
    }
  }

  const submitExtend = (seconds: number) =>
    void runDerived(() => extendCandidate(candidate.id, { seconds }), `延长 ${seconds} 秒`)

  const submitVariant = (stylePrompt: string) =>
    void runDerived(
      () => variantCandidate(candidate.id, stylePrompt ? { style_prompt: stylePrompt } : {}),
      '生成变体',
    )

  const submitRegen = (req: RegenSectionRequest) =>
    void runDerived(
      () => regenSectionCandidate(candidate.id, req),
      `段落重生成 ${SECTION_LABEL[req.section]}${req.occurrence != null && req.occurrence > 1 ? `#${req.occurrence}` : ''}`,
    )

  const togglePanel = (kind: DeriveKind) => setPanel((p) => (p === kind ? null : kind))

  return (
    <div className="card pop" style={{ animationDelay: `${index * 0.12}s` }}>
      <div className="flex items-center gap-4 px-4 py-3">
        <div
          className="cover cursor-pointer"
          style={{ background: index ? '#1c2b1f' : '#232323', border: '1px solid var(--line)' }}
          onClick={onPlay}
          title="试听"
        >
          <canvas ref={canvasRef} className="w-full h-full"></canvas>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-semibold truncate">{title}</span>
            <span
              className="text-[9px] px-1.5 py-0.5 font-bold num"
              style={{ background: 'var(--acc-dim)', color: 'var(--acc)' }}
            >
              AI 质量 {candidate.quality_score}
            </span>
            {candidate.adopted && (
              <span
                className="text-[9px] px-1.5 py-0.5 font-bold"
                style={{ background: 'var(--acc)', color: '#000' }}
              >
                已定稿
              </span>
            )}
          </div>
          <div className="flex gap-1.5 mt-1.5 flex-wrap">
            {(candidate.style_tags.length > 0
              ? candidate.style_tags
              : [VOCAL_LABEL[candidate.vocal], keyLabel(candidate.key), candidate.time_signature]
            ).map((t) => (
              <span key={t} className="text-[10px] px-1.5 py-0.5" style={{ background: 'var(--bg3)', color: 'var(--muted)' }}>
                {t}
              </span>
            ))}
          </div>
        </div>
        <span className="text-[11px] num" style={{ color: 'var(--dim)' }}>
          {formatDuration(candidate.duration_sec)}
        </span>
      </div>
      <div className="flex gap-1 px-4 pb-2">
        {candidate.structure.map((seg, i) => {
          const span = Math.max(0, seg.end_sec - seg.start_sec)
          const width = candidate.duration_sec > 0 ? Math.max(4, (span / candidate.duration_sec) * 100) : 10
          return (
            <div key={i} className="segmini" style={{ width: `${width}%` }} title={`${SECTION_LABEL[seg.section]} · ${seg.bars} 小节`}>
              {SECTION_LABEL[seg.section]}
            </div>
          )
        })}
      </div>
      <div className="flex items-center gap-1.5 px-4 pb-3.5 flex-wrap">
        <button className="iconbtn" title="试听" onClick={onPlay}>
          <svg viewBox="0 0 16 16" fill="currentColor">
            <path d="M5 3l8 5-8 5z" />
          </svg>
        </button>
        {!candidate.adopted && (
          <button className="btn btn-ghost !py-1 !px-2.5 text-[11px]" onClick={() => void onAdopt()}>
            采用定稿
          </button>
        )}
        <button
          className="btn btn-ghost !py-1 !px-2.5 text-[11px]"
          disabled={generating}
          title={generating ? '生成中，请稍候' : '从结尾续写 15~60 秒，生成新子版本'}
          onClick={() => togglePanel('extend')}
        >
          延长
        </button>
        <button
          className="btn btn-ghost !py-1 !px-2.5 text-[11px]"
          disabled={generating}
          title={generating ? '生成中，请稍候' : '同结构换风格，生成新子版本'}
          onClick={() => togglePanel('variant')}
        >
          变体
        </button>
        <button
          className="btn btn-ghost !py-1 !px-2.5 text-[11px]"
          disabled={generating}
          title={generating ? '生成中，请稍候' : '选择段落重生成，其余段保持不变'}
          onClick={() => togglePanel('regen')}
        >
          段落重生成
        </button>
        <span style={{ flex: 1 }}></span>
        <button
          className="btn btn-ghost !py-1 !px-2.5 text-[11px]"
          style={{ color: 'var(--acc)', borderColor: 'var(--acc)' }}
          onClick={() => {
            navigate('/arrange')
            toast(`已送往编曲：${title}（编曲为 V2 功能，占位页）`)
            useStudioStore.getState().logOp(`送往编曲：${title}`)
          }}
        >
          送往编曲 →
        </button>
        <button
          className="btn btn-ghost !py-1 !px-2.5 text-[11px]"
          onClick={() => (workId ? navigate(`/works/${workId}`) : toast('作品详情生成中，请稍候', 'warn'))}
          title="到作品详情导出 WAV / MP3 / MIDI / Stems 与证书"
        >
          导出
        </button>
      </div>
      {panel != null && (
        <DerivePanel
          key={panel}
          kind={panel}
          candidate={candidate}
          busy={busy}
          onSubmitExtend={submitExtend}
          onSubmitVariant={submitVariant}
          onSubmitRegen={submitRegen}
          onClose={() => setPanel(null)}
        />
      )}
    </div>
  )
}
