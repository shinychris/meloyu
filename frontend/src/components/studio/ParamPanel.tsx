import { useMetaStore } from '../../stores/meta'
import { useStudioStore } from '../../stores/studio'
import type { KeyMode, Tonic } from '../../types/api'

const DURATION_PRESETS: Array<{ label: string; value: number }> = [
  { label: '完整歌曲 ≈ 3:30', value: 210 },
  { label: '短片配乐 ≈ 1:00', value: 60 },
  { label: 'Loop ≈ 0:30', value: 30 },
]

/** 参数与模型面板：语言/人声/调性/拍号/时长/模型 + BPM/密度滑杆 + 负向提示 */
export default function ParamPanel() {
  const meta = useMetaStore((s) => s.meta)
  const form = useStudioStore((s) => s.form)
  const { patchForm, markStep } = useStudioStore()
  const limits = meta.generation_limits
  const keyValue = `${form.keyTonic}|${form.keyMode}`

  const onKeyChange = (v: string) => {
    const [tonic, mode] = v.split('|') as [Tonic, KeyMode]
    patchForm({ keyTonic: tonic, keyMode: mode })
    markStep(3)
  }

  return (
    <>
      <div className="grid grid-cols-2 gap-2.5 mt-2">
        <div>
          <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>语言</div>
          <select value={form.language} onChange={(e) => { patchForm({ language: e.target.value as typeof form.language }); markStep(3) }}>
            {meta.languages.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div>
          <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>人声</div>
          <select value={form.vocal} onChange={(e) => { patchForm({ vocal: e.target.value as typeof form.vocal }); markStep(3) }}>
            {meta.vocal_types.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div>
          <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>调性</div>
          <select value={keyValue} onChange={(e) => onKeyChange(e.target.value)}>
            {meta.keys.map((k) => (
              <option key={`${k.tonic}|${k.mode}`} value={`${k.tonic}|${k.mode}`}>{k.label}</option>
            ))}
          </select>
        </div>
        <div>
          <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>拍号</div>
          <select value={form.timeSignature} onChange={(e) => { patchForm({ timeSignature: e.target.value as typeof form.timeSignature }); markStep(3) }}>
            {meta.time_signatures.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
        <div>
          <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>时长</div>
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
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
            {!DURATION_PRESETS.some((p) => p.value === form.durationSec) && (
              <option value="custom">自定义 {form.durationSec}s</option>
            )}
          </select>
        </div>
        <div>
          <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>模型</div>
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
          <span>器乐密度</span>
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
      <div className="mt-2.5">
        <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>排除元素（负向提示）</div>
        <input
          type="text"
          placeholder="例：不要鼓机、不要电音人声"
          maxLength={limits.max_negative_prompt}
          value={form.negativePrompt}
          onChange={(e) => patchForm({ negativePrompt: e.target.value })}
        />
      </div>
    </>
  )
}
