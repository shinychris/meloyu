import { useEffect, useRef, useState } from 'react'
import type { ExportFormat, Task } from '../../types/api'
import { createExport } from '../../api/files'
import { getTask } from '../../api/generation'
import { downloadFileRef } from '../../api/files'
import { downloadCertificate } from '../../api/works'
import { toast } from '../../stores/toast'
import { useT, type TranslationKey } from '../../i18n'

// 格式说明文案走 i18n（work.export.note.*）；WAV/MP3 等为专有名词保留原文
const FORMATS: Array<{ code: ExportFormat; label: string; noteKey: TranslationKey }> = [
  { code: 'wav', label: 'WAV', noteKey: 'work.export.note.wav' },
  { code: 'mp3', label: 'MP3', noteKey: 'work.export.note.mp3' },
  { code: 'midi', label: 'MIDI', noteKey: 'work.export.note.midi' },
  { code: 'stems', label: 'Stems', noteKey: 'work.export.note.stems' },
]

type BusyMap = Partial<Record<ExportFormat, number>>

/** 导出面板：WAV / MP3 / MIDI / Stems + 授权证书（导出任务轮询完成后自动下载） */
export default function ExportPanel({ versionId }: { versionId: string }) {
  const t = useT()
  const [busy, setBusy] = useState<BusyMap>({})
  const [certBusy, setCertBusy] = useState(false)
  const timers = useRef<number[]>([])
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      timers.current.forEach((tm) => window.clearTimeout(tm))
    }
  }, [])

  const schedule = (taskId: string, format: ExportFormat, fails: number) => {
    const timer = window.setTimeout(async () => {
      try {
        const task: Task = await getTask(taskId)
        if (!mounted.current) return
        if (task.status === 'succeeded') {
          setBusy((b) => ({ ...b, [format]: undefined }))
          if (task.result && 'files' in task.result && task.result.files.length > 0) {
            for (const f of task.result.files) {
              await downloadFileRef(f, `${format}_${f.file_id}`)
            }
            toast(t('work.export.toast.done', { format: format.toUpperCase(), n: task.result.files.length }))
          } else {
            toast(t('work.export.toast.noFiles'))
          }
        } else if (task.status === 'failed' || task.status === 'canceled') {
          setBusy((b) => ({ ...b, [format]: undefined }))
          toast(task.error?.message ?? t('work.export.failed'), 'bad')
        } else {
          setBusy((b) => ({ ...b, [format]: task.progress }))
          schedule(taskId, format, 0)
        }
      } catch {
        if (!mounted.current) return
        if (fails >= 4) {
          setBusy((b) => ({ ...b, [format]: undefined }))
          toast(t('work.export.toast.pollBroken'), 'bad')
        } else {
          schedule(taskId, format, fails + 1)
        }
      }
    }, 1500)
    timers.current.push(timer)
  }

  const runExport = async (format: ExportFormat) => {
    if (busy[format] !== undefined) return
    setBusy((b) => ({ ...b, [format]: 0 }))
    try {
      const { task } = await createExport({ version_id: versionId, format })
      schedule(task.id, format, 0)
    } catch {
      setBusy((b) => ({ ...b, [format]: undefined }))
      /* 40901 无活跃候选等已 toast */
    }
  }

  const onCert = async () => {
    if (certBusy) return
    setCertBusy(true)
    try {
      await downloadCertificate(versionId, `${versionId}_certificate.json`)
      toast(t('work.export.toast.certStarted'))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setCertBusy(false)
    }
  }

  return (
    <div className="card p-4">
      <div className="label mb-3">{t('work.export.title')}</div>
      <div className="grid grid-cols-2 gap-2">
        {FORMATS.map((f) => {
          const pct = busy[f.code]
          return (
            <button
              key={f.code}
              className="btn btn-ghost !py-2 text-[11px] text-left"
              disabled={pct !== undefined}
              onClick={() => void runExport(f.code)}
            >
              <span className="font-bold">{t('work.export.run', { format: f.label })}</span>
              <span className="block text-[9px] font-normal mt-0.5" style={{ color: 'var(--dim)' }}>
                {pct !== undefined ? t('work.export.processing', { n: pct }) : t(f.noteKey)}
              </span>
            </button>
          )
        })}
      </div>
      <button className="btn btn-acc w-full mt-2 !py-2 text-[11px] font-bold" disabled={certBusy} onClick={() => void onCert()}>
        {certBusy ? t('work.export.generating') : t('work.export.certificate')}
      </button>
      <div className="text-[9px] mt-2 leading-relaxed" style={{ color: 'var(--dim)' }}>
        {t('work.export.footnote')}
      </div>
    </div>
  )
}
