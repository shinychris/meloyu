import { useState } from 'react'
import { useMetaStore } from '../../stores/meta'
import { useStudioStore } from '../../stores/studio'
import { useT, type TranslationKey } from '../../i18n'
import type { KeyMode, Tonic } from '../../types/api'
import { toast } from '../../stores/toast'
import VoicePanel from './VoicePanel'

const DURATION_PRESETS: Array<{ label: TranslationKey; value: number }> = [
  { label: 'studio.param.durationFull', value: 210 },
  { label: 'studio.param.durationShort', value: 60 },
  { label: 'studio.param.durationLoop', value: 30 },
]

/** 参数与模型面板：语言/人声/调性/拍号/时长/模型 + BPM/密度滑杆 + 负向提示 */
export default function ParamPanel() {
  const t = useT()
  const meta = useMetaStore((s) => s.meta)
  const form = useStudioStore((s) => s.form)
  const { patchForm, markStep } = useStudioStore()
  const limits = meta.generation_limits
  const keyValue = `${form.keyTonic}|${form.keyMode}`
  const [voiceOpen, setVoiceOpen] = useState(false)

  const onKeyChange = (v: string) => {
    const [tonic, mode] = v.split('|') as [Tonic, KeyMode]
    patchForm({ keyTonic: tonic, keyMode: mode })
    markStep(3)
  }

  const applyTaste = async () => {
    try {
      const { getTaste } = await import('../../api/taste')
      const r = await getTaste()
      const p = r.profile
      if (r.sample_count === 0 || p.bpm == null) {
        toast(t('studio.taste.empty'), 'warn')
        return
      }
      const patch: Parameters<typeof patchForm>[0] = { bpm: p.bpm, density: p.density ?? form.density }
      if (p.key) {
        const [tonic, mode] = p.key.split(' ') as [Tonic, KeyMode]
        patch.keyTonic = tonic
        patch.keyMode = mode
      }
      if (p.vocal) patch.vocal = p.vocal as typeof form.vocal
      patchForm(patch)
      markStep(3)
      toast(t('studio.taste.applied', { n: r.sample_count }))
    } catch {
      /* 拦截器已 toast */
    }
  }

  return (
    <>
      <div className="flex items-center justify-between mt-2">
        <span className="text-[10px]" style={{ color: 'var(--dim)' }}>{t('studio.param.label')}</span>
        <button className="text-[9px] underline" style={{ color: 'var(--dim)' }} onClick={() => void applyTaste()}>
          {t('studio.taste.apply')}
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2.5 mt-2">
        <div>
          <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>{t('studio.param.language')}</div>
          <select value={form.language} onChange={(e) => { patchForm({ language: e.target.value as typeof form.language }); markStep(3) }}>
            {meta.languages.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div>
          <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>{t('studio.param.vocal')}</div>
          <select value={form.vocal} onChange={(e) => { patchForm({ vocal: e.target.value as typeof form.vocal }); markStep(3) }}>
            {meta.vocal_types.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          {form.vocal === 'voice_clone' && !form.voiceProfileId && (
            <div className="text-[9px] mt-1" style={{ color: 'var(--bad)' }}>{t('studio.voice.pickFirst')}</div>
          )}
          {form.vocal !== 'voice_clone' && !voiceOpen && (
            <button className="text-[9px] mt-1 underline" style={{ color: 'var(--dim)' }} onClick={() => setVoiceOpen(true)}>
              {t('studio.voice.manage')}
            </button>
          )}
        </div>
        <div>
          <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>{t('studio.param.key')}</div>
          <select value={keyValue} onChange={(e) => onKeyChange(e.target.value)}>
            {meta.keys.map((k) => (
              <option key={`${k.tonic}|${k.mode}`} value={`${k.tonic}|${k.mode}`}>{k.label}</option>
            ))}
          </select>
        </div>
        <div>
          <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>{t('studio.param.timeSignature')}</div>
          <select value={form.timeSignature} onChange={(e) => { patchForm({ timeSignature: e.target.value as typeof form.timeSignature }); markStep(3) }}>
            {meta.time_signatures.map((ts) => (
              <option key={ts} value={ts}>{ts}</option>
            ))}
          </select>
        </div>
        <div>
          <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>{t('studio.param.duration')}</div>
          <select
            value={DURATION_PRESETS.some((p) => p.value === form.durationSec) ? form.durationSec : 'custom'}
            onChange={(e) => {
              const v = Number(e.target.value)
              if (!Number.isNaN(v)) {
                patchForm({ durationSec: Math.min(limits.max_duration_sec, Math.max(limits.min_duration_sec, v)) })
                markStep(3)
              }
            }}
          >
            {DURATION_PRESETS.map((p) => (
              <option key={p.value} value={p.value}>{t(p.label)}</option>
            ))}
            {!DURATION_PRESETS.some((p) => p.value === form.durationSec) && (
              <option value="custom">{t('studio.param.durationCustom', { n: form.durationSec })}</option>
            )}
          </select>
        </div>
        <div>
          <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>{t('studio.param.model')}</div>
          <select value={form.model} onChange={(e) => { patchForm({ model: e.target.value as typeof form.model }); markStep(3) }}>
            {meta.models.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-3">
        <div className="flex justify-between text-[10px] mb-1.5" style={{ color: 'var(--dim)' }}>
          <span>BPM</span>
          <span className="num">{form.bpm}</span>
        </div>
        <input
          type="range"
          min={limits.min_bpm}
          max={limits.max_bpm}
          value={form.bpm}
          onChange={(e) => { patchForm({ bpm: Number(e.target.value) }); markStep(3) }}
        />
      </div>
      <div className="mt-2.5">
        <div className="flex justify-between text-[10px] mb-1.5" style={{ color: 'var(--dim)' }}>
          <span>{t('studio.param.density')}</span>
          <span className="num">{form.density}%</span>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          value={form.density}
          onChange={(e) => { patchForm({ density: Number(e.target.value) }); markStep(3) }}
        />
      </div>
      {(form.vocal === 'voice_clone' || voiceOpen) && <VoicePanel />}

      <div className="mt-2.5">
        <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>{t('studio.param.negative')}</div>
        <input
          type="text"
          placeholder={t('studio.param.negativePlaceholder')}
          maxLength={limits.max_negative_prompt}
          value={form.negativePrompt}
          onChange={(e) => patchForm({ negativePrompt: e.target.value })}
        />
      </div>
    </>
  )
}
