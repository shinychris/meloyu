import { useEffect, useRef, useState } from 'react'
import type { HumAnalysisData } from '../../types/api'
import { analyzeHum } from '../../api/hum'
import { toast } from '../../stores/toast'
import { useT } from '../../i18n'

/** 录音 → mono 22.05kHz 16bit wav（复用 ReferencePanel 的渲染口径）。 */
async function recordChunkToWav(chunk: Blob): Promise<ArrayBuffer> {
  const raw = await chunk.arrayBuffer()
  const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  const ctx = new Ctx()
  try {
    const buf = await ctx.decodeAudioData(raw.slice(0))
    const targetRate = 22050
    const off = new OfflineAudioContext(1, Math.max(1, Math.ceil(buf.duration * targetRate)), targetRate)
    const src = off.createBufferSource()
    src.buffer = buf
    src.connect(off.destination)
    src.start()
    const rendered = await off.startRendering()
    const samples = rendered.getChannelData(0)
    const pcm = new Int16Array(samples.length)
    for (let i = 0; i < samples.length; i++) {
      const v = Math.max(-1, Math.min(1, samples[i]))
      pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff
    }
    const header = new ArrayBuffer(44)
    const dv = new DataView(header)
    const write = (o: number, str: string) => {
      for (let i = 0; i < str.length; i++) dv.setUint8(o + i, str.charCodeAt(i))
    }
    write(0, 'RIFF')
    dv.setUint32(4, 36 + pcm.length * 2, true)
    write(8, 'WAVE')
    write(12, 'fmt ')
    dv.setUint32(16, 16, true)
    dv.setUint16(20, 1, true)
    dv.setUint16(22, 1, true)
    dv.setUint32(24, targetRate, true)
    dv.setUint32(28, targetRate * 2, true)
    dv.setUint16(32, 2, true)
    dv.setUint16(34, 16, true)
    write(36, 'data')
    dv.setUint32(40, pcm.length * 2, true)
    const out = new Uint8Array(44 + pcm.length * 2)
    out.set(new Uint8Array(header), 0)
    out.set(new Uint8Array(pcm.buffer), 44)
    return out.buffer
  } finally {
    void ctx.close()
  }
}

const MAX_SEC = 30

/**
 * 哼唱成歌录音弹窗（v0.11.0）：MediaRecorder 录 ≤30s → 浏览器渲染 mono wav →
 * POST /hum/analyze（真实 f0 提取）→ 展示音高轮廓 → 「应用」写入表单
 * params.hum_melody（生成时由引擎按音程关系映射为人声旋律）。
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
          const wav = await recordChunkToWav(new Blob(chunksRef.current, { type: 'audio/webm' }))
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
    <div className="fixed inset-0 z-[95] flex items-center justify-center" style={{ background: 'rgba(0,0,0,.72)' }}>
      <div className="card pop w-[440px] p-6">
        <div className="text-[15px] font-bold">{t('studio.hum.title')}</div>
        <div className="text-[12px] mt-2 leading-relaxed" style={{ color: 'var(--muted)' }}>
          {t('studio.hum.desc')}
        </div>

        <div className="flex items-center gap-3 mt-4">
          {!recording ? (
            <button className="btn btn-acc !py-1.5 !px-4 text-[12px]" onClick={() => void start()} disabled={analyzing}>
              ● {analyzing ? t('studio.hum.analyzing') : t('studio.hum.record')}
            </button>
          ) : (
            <button className="btn btn-ghost !py-1.5 !px-4 text-[12px]" onClick={stop}>
              ■ {t('studio.hum.stop')} ({elapsed}s/{MAX_SEC}s)
            </button>
          )}
        </div>

        {result && (
          <div className="mt-4">
            <div className="text-[11px] num" style={{ color: 'var(--muted)' }}>
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
                    className="flex-1 rounded-sm"
                    style={{ height: h, background: 'var(--acc)', opacity: 0.75 }}
                    title={`${n.semi >= 0 ? '+' : ''}${n.semi}`}
                  />
                )
              })}
            </div>
            <div className="flex gap-2 justify-end mt-4">
              <button className="btn btn-ghost !py-1.5 !px-4 text-[12px]" onClick={onClose}>
                {t('common.cancel')}
              </button>
              <button className="btn btn-acc !py-1.5 !px-4 text-[12px]" onClick={apply}>
                {t('studio.hum.apply')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
