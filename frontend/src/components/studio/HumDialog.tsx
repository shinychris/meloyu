import { useEffect, useRef, useState } from 'react'
import type { HumAnalysisData } from '../../types/api'
import { analyzeHum } from '../../api/hum'
import { decodeToWav } from '../../lib/audio'
import { toast } from '../../stores/toast'
import { useT } from '../../i18n'

const MAX_SEC = 30

/**
 * 哼唱成歌录音弹窗（v0.11.0）：MediaRecorder 录 ≤30s → 浏览器渲染 mono wav →
 * POST /hum/analyze（真实 f0 提取）→ 展示音高轮廓 → 「应用」写入表单
 * params.hum_melody（生成时由引擎按音程关系映射为人声旋律）。
 * WAV 编码复用 lib/audio 的 decodeToWav（F-FE-10：删除本地重复实现；
 * mimeType 以 MediaRecorder 实际值为准，兜底 audio/webm）。
 */
export default function HumDialog({ open, onClose, onApply }: {
  open: boolean
  onClose: () => void
  onApply: (humMelody: number[][], bpmHint: number) => void
}) {
  const t = useT()
  const [recording, setRecording] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState<HumAnalysisData | null>(null)
  const recRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<number>(0)

  useEffect(() => () => {
    window.clearInterval(timerRef.current)
    if (recRef.current?.state === 'recording') recRef.current.stop()
  }, [])

  if (!open) return null

  const start = async () => {
    setResult(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream)
      chunksRef.current = []
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      rec.onstop = async () => {
        stream.getTracks().forEach((tr) => tr.stop())
        setAnalyzing(true)
        try {
          const wav = await decodeToWav(
            await new Blob(chunksRef.current, { type: rec.mimeType || 'audio/webm' }).arrayBuffer(),
          )
          setResult(await analyzeHum(wav))
        } catch {
          /* 拦截器已 toast（太短/信号弱/格式） */
        } finally {
          setAnalyzing(false)
        }
      }
      recRef.current = rec
      rec.start()
      setRecording(true)
      setElapsed(0)
      timerRef.current = window.setInterval(() => {
        setElapsed((s) => {
          if (s + 1 >= MAX_SEC) {
            window.clearInterval(timerRef.current)
            if (recRef.current?.state === 'recording') recRef.current.stop()
            setRecording(false)
          }
          return s + 1
        })
      }, 1000)
    } catch {
      toast(t('studio.hum.micDenied'), 'bad')
    }
  }

  const stop = () => {
    window.clearInterval(timerRef.current)
    if (recRef.current?.state === 'recording') recRef.current.stop()
    setRecording(false)
  }

  const apply = () => {
    if (!result) return
    onApply(result.hum_melody, result.bpm_hint)
    toast(t('studio.hum.applied', { n: result.note_count }))
    onClose()
  }

  const semiRange = result
    ? Math.max(...result.notes.map((n) => n.semi)) - Math.min(...result.notes.map((n) => n.semi))
    : 0

  return (
    <div className="modal-overlay">
      <div className="card pop w-[440px] p-6">
        <div className="text-md font-bold">{t('studio.hum.title')}</div>
        <div className="text-sm mt-2 leading-relaxed text-muted">
          {t('studio.hum.desc')}
        </div>

        <div className="flex items-center gap-3 mt-4">
          {!recording ? (
            <button className="btn btn-acc btn-md" onClick={() => void start()} disabled={analyzing}>
              ● {analyzing ? t('studio.hum.analyzing') : t('studio.hum.record')}
            </button>
          ) : (
            <button className="btn btn-ghost btn-md" onClick={stop}>
              ■ {t('studio.hum.stop')} ({elapsed}s/{MAX_SEC}s)
            </button>
          )}
        </div>

        {result && (
          <div className="mt-4">
            <div className="text-xs num text-muted">
              {t('studio.hum.result', {
                n: result.note_count,
                sec: result.duration_sec,
                bpm: result.bpm_hint,
                conf: Math.round(result.confidence * 100),
              })}
            </div>
            {/* 音高轮廓条（半音相对值，纵向可视化） */}
            <div className="flex items-end gap-0.5 h-16 mt-2" data-testid="hum-contour">
              {result.notes.slice(0, 64).map((n, i) => {
                const lo = Math.min(...result.notes.map((x) => x.semi))
                const h = semiRange > 0 ? ((n.semi - lo) / semiRange) * 56 + 4 : 30
                return (
                  <div
                    key={i}
                    className="flex-1"
                    style={{ height: h, background: 'var(--acc)', opacity: 0.75 }}
                    title={`${n.semi >= 0 ? '+' : ''}${n.semi}`}
                  />
                )
              })}
            </div>
            <div className="flex gap-2 justify-end mt-4">
              <button className="btn btn-ghost btn-md" onClick={onClose}>
                {t('common.cancel')}
              </button>
              <button className="btn btn-acc btn-md" onClick={apply}>
                {t('studio.hum.apply')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
