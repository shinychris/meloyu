import { useEffect, useRef, useState } from 'react'
import type { ExportFormat, Task } from '../../types/api'
import { createExport } from '../../api/files'
import { getTask } from '../../api/generation'
import { downloadFileRef } from '../../api/files'
import { downloadCertificate } from '../../api/works'
import { toast } from '../../stores/toast'

const FORMATS: Array<{ code: ExportFormat; label: string; note: string }> = [
  { code: 'wav', label: 'WAV', note: '48kHz / 24bit 母带' },
  { code: 'mp3', label: 'MP3', note: '320k CBR' },
  { code: 'midi', label: 'MIDI', note: 'melody/chords/bass/drums ×4' },
  { code: 'stems', label: 'Stems', note: 'vocals/drums/bass/other ZIP' },
]

type BusyMap = Partial<Record<ExportFormat, number>>

/** 导出面板：WAV / MP3 / MIDI / Stems + 授权证书（导出任务轮询完成后自动下载） */
export default function ExportPanel({ versionId }: { versionId: string }) {
  const [busy, setBusy] = useState<BusyMap>({})
  const [certBusy, setCertBusy] = useState(false)
  const timers = useRef<number[]>([])
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      timers.current.forEach((t) => window.clearTimeout(t))
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
            toast(`导出完成：${format.toUpperCase()} 已开始下载（${task.result.files.length} 个文件）`)
          } else {
            toast('导出完成，但未返回文件列表')
          }
        } else if (task.status === 'failed' || task.status === 'canceled') {
          setBusy((b) => ({ ...b, [format]: undefined }))
          toast(task.error?.message ?? '导出失败', 'bad')
        } else {
          setBusy((b) => ({ ...b, [format]: task.progress }))
          schedule(taskId, format, 0)
        }
      } catch {
        if (!mounted.current) return
        if (fails >= 4) {
          setBusy((b) => ({ ...b, [format]: undefined }))
          toast('导出任务查询中断', 'bad')
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
      toast('授权证书 JSON 已开始下载')
    } catch {
      /* 拦截器已 toast */
    } finally {
      setCertBusy(false)
    }
  }

  return (
    <div className="card p-4">
      <div className="label mb-3">导出与证书</div>
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
              <span className="font-bold">导出 {f.label}</span>
              <span className="block text-[9px] font-normal mt-0.5" style={{ color: 'var(--dim)' }}>
                {pct !== undefined ? `处理中 ${pct}%…` : f.note}
              </span>
            </button>
          )
        })}
      </div>
      <button className="btn btn-acc w-full mt-2 !py-2 text-[11px] font-bold" disabled={certBusy} onClick={() => void onCert()}>
        {certBusy ? '生成中…' : '下载授权证书 JSON'}
      </button>
      <div className="text-[9px] mt-2 leading-relaxed" style={{ color: 'var(--dim)' }}>
        导出不扣积分；需先在候选列表「采用定稿」。证书含人类创作留痕与 SHA-256 内容指纹。
      </div>
    </div>
  )
}
