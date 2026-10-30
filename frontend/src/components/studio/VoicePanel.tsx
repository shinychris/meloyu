import { useEffect, useRef, useState } from 'react'
import type { VoiceProfile } from '../../types/api'
import { deleteVoiceProfile, enrollVoiceProfile, listVoiceProfiles, submitVoiceSample } from '../../api/voice'
import { startRecording, type RecordingSession } from '../../lib/audio'
import { useStudioStore } from '../../stores/studio'
import { confirmDialog } from '../../stores/confirm'
import { toast } from '../../stores/toast'
import { useT } from '../../i18n'

/**
 * 我的音色面板（FR-5）：双随机短语活体验证注册 → 已验证档案选用。
 * 流程：注册（命名）→ 朗读短语1（录音）→ 朗读短语2（防重放）→ 同人校验通过 →
 * 可在生成中使用「我的音色」（参数级音色适配：音域/共振峰/亮度）。
 * 边界如实标注：一致性校验为统计特征启发式，非神经网络声纹模型。
 */
export default function VoicePanel() {
  const t = useT()
  const [profiles, setProfiles] = useState<VoiceProfile[]>([])
  const [nameDraft, setNameDraft] = useState('')
  const [active, setActive] = useState<VoiceProfile | null>(null)
  /** 本地推进标记：样本1提交后进入第 2 步（phrase2 已下发） */
  const [sampleStep, setSampleStep] = useState<1 | 2>(1)
  const [recording, setRecording] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const recRef = useRef<RecordingSession | null>(null)
  const form = useStudioStore((s) => s.form)
  const { patchForm, markStep, logOp } = useStudioStore()

  const refresh = () => {
    listVoiceProfiles()
      .then((r) => setProfiles(r.items))
      .catch(() => {})
  }
  useEffect(refresh, [])

  // F-FE-01（P1）：录音中途卸载组件时终止录音会话——停止 MediaRecorder 并释放
  // getUserMedia 轨道，麦克风不再被占用（范式同 HumDialog 的卸载清理）
  useEffect(
    () => () => {
      const rec = recRef.current
      recRef.current = null
      if (rec) void rec.stop()
    },
    [],
  )

  const startEnroll = async () => {
    const name = nameDraft.trim()
    if (!name) {
      toast(t('studio.voice.toast.nameRequired'), 'warn')
      return
    }
    try {
      const p = await enrollVoiceProfile(name)
      setActive(p)
      setSampleStep(1)
      setNameDraft('')
      refresh()
    } catch {
      /* 拦截器已 toast */
    }
  }

  const beginRecording = async () => {
    if (recording || !active) return
    try {
      recRef.current = await startRecording()
      setRecording(true)
    } catch {
      toast(t('studio.voice.toast.micDenied'), 'bad')
    }
  }

  const finishRecording = async () => {
    if (!recording || !recRef.current || !active) return
    setRecording(false)
    setSubmitting(true)
    try {
      const wav = await recRef.current.stop()
      recRef.current = null
      const step = sampleStep
      const updated = await submitVoiceSample(active.id, step, wav)
      if (step === 1) {
        setSampleStep(2)
        setActive(updated)
      }
      if (updated.status === 'verified') {
        patchForm({ vocal: 'voice_clone', voiceProfileId: updated.id })
        markStep(3)
        logOp(t('studio.voice.log.verified', { name: updated.name }))
        toast(t('studio.voice.toast.verified'))
        setActive(null)
      } else if (step === 1) {
        toast(t('studio.voice.toast.phrase2Ready'))
      } else {
        toast(
          t('studio.voice.toast.verifyFailed', { n: updated.verify_attempts, score: Math.round((updated.verify_score ?? 0) * 100) }),
          'warn',
        )
      }
      refresh()
    } catch {
      /* 拦截器已 toast（校验失败次数上限/采样过短等） */
      refresh()
    } finally {
      setSubmitting(false)
    }
  }

  // F-FE-16：普通事件处理函数不以 use 前缀命名（原 useProfile 触发 hooks 规则误报，
  // 是 rules-of-hooks 全局降级的诱因之一）
  const applyProfile = (p: VoiceProfile) => {
    patchForm({ vocal: 'voice_clone', voiceProfileId: p.id })
    markStep(3)
    toast(t('studio.voice.toast.selected', { name: p.name }))
  }

  const removeProfile = async (p: VoiceProfile) => {
    // F-FE-22：删除音色档案为破坏性操作，接 confirmDialog({ danger: true }) 二次确认
    const ok = await confirmDialog({
      title: t('studio.voice.confirm.deleteTitle', { name: p.name }),
      description: t('studio.voice.confirm.deleteDesc'),
      confirmText: t('studio.voice.delete'),
      danger: true,
    })
    if (!ok) return
    try {
      await deleteVoiceProfile(p.id)
      if (form.voiceProfileId === p.id) patchForm({ vocal: 'female_air', voiceProfileId: undefined })
      refresh()
    } catch {
      /* 拦截器已 toast */
    }
  }

  const verified = profiles.filter((p) => p.status === 'verified')
  const phrase = sampleStep === 2 ? active?.phrase2 : active?.phrase1

  return (
    <div className="mt-3 card p-3" data-testid="voice-panel">
      <div className="label">{t('studio.voice.title')}</div>
      <div className="text-2xs mt-1 leading-relaxed text-dim">
        {t('studio.voice.hint')}
      </div>

      {verified.length > 0 && (
        <div className="mt-2 space-y-1">
          {verified.map((p) => (
            <div key={p.id} className="flex items-center gap-2">
              <button
                className={`btn btn-sm ${form.voiceProfileId === p.id ? 'btn-acc' : 'btn-ghost'}`}
                onClick={() => applyProfile(p)}
              >
                {p.name}
                {form.voiceProfileId === p.id ? ' ✓' : ''}
              </button>
              <button
                className="iconbtn"
                title={t('studio.voice.delete')}
                onClick={() => void removeProfile(p)}
              >
                <svg viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.4" fill="none">
                  <path d="M3 4h10M6 4V2.5h4V4M5 4l.7 9h4.6l.7-9" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      {active ? (
        <div className="mt-2">
          <div className="text-2xs text-muted">
            {sampleStep === 2 ? t('studio.voice.step2') : t('studio.voice.step1')}
          </div>
          <div className="text-md font-bold mt-1.5 leading-snug" data-testid="voice-phrase">
            “{phrase}”
          </div>
          <div className="flex gap-2 mt-2">
            {!recording ? (
              <button className="btn btn-acc btn-sm" disabled={submitting} onClick={() => void beginRecording()}>
                {t('studio.voice.record')}
              </button>
            ) : (
              <button className="btn btn-acc btn-sm" onClick={() => void finishRecording()}>
                ⏺ {t('studio.voice.stop')}
              </button>
            )}
            <button className="btn btn-ghost btn-sm" onClick={() => setActive(null)}>
              {t('common.cancel')}
            </button>
          </div>
          {recording && (
            <div className="text-2xs mt-1.5 text-acc">
              {t('studio.voice.recording')}
            </div>
          )}
        </div>
      ) : (
        <div className="flex gap-1.5 mt-2">
          <input
            type="text"
            className="!text-xs flex-1"
            maxLength={60}
            placeholder={t('studio.voice.namePlaceholder')}
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
          />
          <button className="btn btn-ghost btn-sm" onClick={() => void startEnroll()}>
            {t('studio.voice.enroll')}
          </button>
        </div>
      )}

      <div className="text-2xs mt-1.5 leading-relaxed text-dim">
        {t('studio.voice.compliance')}
      </div>
    </div>
  )
}
