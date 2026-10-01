import { useRef, useState } from 'react'
import type { ReferenceTrack } from '../../types/api'
import { attachAnalysisWav, uploadReferenceTrack } from '../../api/reference'
import { useStudioStore } from '../../stores/studio'
import { toast } from '../../stores/toast'
import { useT } from '../../i18n'
import type { Tonic } from '../../types/api'

import { decodeToWav } from '../../lib/audio'

const ACCEPT = '.mp3,.wav,.m4a'
const MAX_BYTES = 50 * 1024 * 1024

/**
 * 参考音频面板（FR-4）：上传（权利确认勾选）→ wav 即时分析 / mp3/m4a 浏览器解码补传
 * → 分析特征卡（BPM/调性/能量）→ 应用到生成参数 + 挂到本次生成（reference_track_id）。
 * 合规：参考非采样（特征级），notice 由后端返回固定双语。
 */
export default function ReferencePanel({ onClose }: { onClose: () => void }) {
  const t = useT()
  const fileInput = useRef<HTMLInputElement>(null)
  const [ack, setAck] = useState(false)
  const [busy, setBusy] = useState(false)
  const referenceTrack = useStudioStore((s) => s.referenceTrack)
  const { setReferenceTrack, clearReferenceTrack, patchForm, markStep, logOp } = useStudioStore()

  const onPick = async (file: File | undefined) => {
    if (!file || busy) return
    if (file.size > MAX_BYTES) {
      toast(t('studio.ref.toast.tooLarge'), 'warn')
      return
    }
    if (!ack) {
      toast(t('studio.ref.toast.ackRequired'), 'warn')
      return
    }
    setBusy(true)
    try {
      let track: ReferenceTrack = await uploadReferenceTrack(file.name, await file.arrayBuffer())
      if (!track.analyzed) {
        // mp3/m4a：浏览器解码渲染补传后服务端分析
        track = await attachAnalysisWav(track.id, await decodeToWav(await file.arrayBuffer()))
      }
      if (!track.analyzed) {
        toast(t('studio.ref.toast.analyzeFailed'), 'bad')
        return
      }
      setReferenceTrack(track)
      applyParams(track)
      toast(t('studio.ref.toast.ready', { name: track.name }))
    } catch {
      /* 拦截器已 toast（超时长/格式错误 40001 等） */
    } finally {
      setBusy(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  /** 分析特征 → 生成参数（用户可再改；值与提交时服务端覆盖一致） */
  const applyParams = (track: ReferenceTrack) => {
    const a = track.analysis!
    patchForm({
      bpm: a.bpm,
      keyTonic: a.key_tonic as Tonic,
      keyMode: a.key_mode,
      density: Math.round(a.energy * 100),
    })
    markStep(3)
    logOp(t('studio.ref.log.applied', { bpm: a.bpm, key: `${a.key_tonic} ${a.key_mode}` }))
  }

  const onRemove = () => {
    clearReferenceTrack()
    onClose()
  }

  return (
    <div className="mt-3 card p-3" data-testid="reference-panel">
      <div className="flex items-center justify-between">
        <div className="label">{t('studio.ref.title')}</div>
        <button className="iconbtn" title={t('common.close')} onClick={onClose}>
          <svg viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.6" fill="none">
            <path d="M3 3l10 10M13 3L3 13" />
          </svg>
        </button>
      </div>

      {referenceTrack ? (
        <div className="mt-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold truncate">{referenceTrack.name}</span>
            {referenceTrack.analysis && (
              <span className="badge badge-acc num">
                {referenceTrack.analysis.bpm} BPM · {referenceTrack.analysis.key_tonic}{' '}
                {referenceTrack.analysis.key_mode === 'major' ? t('studio.ref.major') : t('studio.ref.minor')}
              </span>
            )}
            <button className="btn btn-ghost btn-sm ml-auto" onClick={() => referenceTrack && applyParams(referenceTrack)}>
              {t('studio.ref.applyParams')}
            </button>
          </div>
          <div className="text-2xs mt-1.5 leading-relaxed text-dim">
            {t('studio.ref.attachedNote')}
          </div>
          <button className="btn btn-ghost w-full mt-2 btn-sm" onClick={onRemove}>
            {t('studio.ref.remove')}
          </button>
        </div>
      ) : (
        <>
          <label className="flex items-start gap-1.5 mt-2 text-2xs cursor-pointer text-muted">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5" />
            <span className="leading-relaxed">{t('studio.ref.ack')}</span>
          </label>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => void onPick(e.target.files?.[0])}
          />
          <button
            className="btn btn-ghost w-full mt-2 btn-md"
            disabled={busy || !ack}
            onClick={() => fileInput.current?.click()}
          >
            {busy ? t('studio.ref.analyzing') : t('studio.ref.pick')}
          </button>
          <div className="text-2xs mt-1.5 leading-relaxed text-dim">
            {t('studio.ref.hint')}
          </div>
        </>
      )}
    </div>
  )
}
