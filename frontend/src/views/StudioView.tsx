import { useNavigate } from 'react-router-dom'
import { useStudioStore } from '../stores/studio'
import { useMetaStore } from '../stores/meta'
import { toast } from '../stores/toast'
import { countStructureTags } from '../lib/structure'
import StepBar from '../components/studio/StepBar'
import InspireBox from '../components/studio/InspireBox'
import ParamPanel from '../components/studio/ParamPanel'
import GenProgress from '../components/studio/GenProgress'
import CandidateCard from '../components/studio/CandidateCard'
import VersionTree from '../components/studio/VersionTree'

const MODE_HINTS: Record<string, string> = {
  simple: '一句话模式：用自然语言描述整首歌',
  custom: '自定义模式：风格 + 结构标签歌词 + 参数',
  ref: '参考音频：V1.1 上线（上传音频作风格参考）',
  hum: '哼唱成歌：V1.1 上线（录一段哼唱，AI 补全）',
}

/** 创作工作台（原型核心视图：左控制 / 中结果 / 右版本树） */
export default function StudioView() {
  const navigate = useNavigate()
  const form = useStudioStore((s) => s.form)
  const { patchForm, markStep, submitGeneration } = useStudioStore()
  const task = useStudioStore((s) => s.task)
  const candidates = useStudioStore((s) => s.candidates)
  const submitting = useStudioStore((s) => s.submitting)
  const failureMessage = useStudioStore((s) => s.failureMessage)
  const workTitle = useStudioStore((s) => s.workTitle)
  const meta = useMetaStore((s) => s.meta)

  const creditCost = meta.models.find((m) => m.value === form.model)?.credit_cost ?? 12
  const modelLabel = meta.models.find((m) => m.value === form.model)?.label ?? 'V1 Pro'
  const tagCount = countStructureTags(form.lyrics)
  const generating =
    submitting || (task != null && (task.status === 'queued' || task.status === 'running'))

  const onMode = (mode: string) => {
    if (mode === 'ref' || mode === 'hum') {
      toast(MODE_HINTS[mode], 'warn')
      return
    }
    patchForm({ mode: mode as typeof form.mode })
    markStep(1)
    toast(MODE_HINTS[mode])
  }

  const insertTag = (tag: string) => {
    patchForm({ lyrics: `${form.lyrics}\n${tag}\n` })
    markStep(2)
  }

  const randomInspire = () => {
    const inspiration = meta.inspiration
    const pickFrom = (list: string[]) =>
      list.length > 0 ? list[Math.floor(Math.random() * list.length)] : ''
    const next = {
      scene: pickFrom(inspiration.scenes),
      mood: pickFrom(inspiration.moods),
      genre: pickFrom(inspiration.genres),
      inst: pickFrom(inspiration.instruments),
    }
    useStudioStore.setState({ inspire: next })
    useStudioStore.getState().applyInspireToPrompt(next)
    markStep(1)
    useStudioStore.getState().logOp(
      `灵感指引：${[next.genre, next.mood, next.inst, next.scene].filter(Boolean).join(' / ')}`,
    )
  }

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4">
        <div className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <div className="label">Studio / 创作工作台</div>
            <h1 className="text-[28px] font-extrabold tracking-tight mt-1">从一句描述，到可发行的歌</h1>
          </div>
          <div className="flex items-center gap-3 text-[11px]" style={{ color: 'var(--muted)' }}>
            <span className="flex items-center gap-2">
              <span className="dot" style={{ background: 'var(--acc)' }}></span>
              {modelLabel} · 中文人声优化
            </span>
            <span className="num" style={{ color: 'var(--dim)' }}>
              本地演示引擎
            </span>
          </div>
        </div>
        <StepBar />
      </header>

      <div className="grid grid-cols-[360px_1fr_200px] rule-t flex-1 min-h-0">
        {/* 左：控制列 */}
        <div className="border-r px-6 py-5 overflow-y-auto" style={{ borderColor: 'var(--line)' }}>
          <div className="label">模式</div>
          <div className="flex gap-1.5 mt-2 flex-wrap">
            <span className={`chip ${form.mode === 'simple' ? 'on' : ''}`} onClick={() => onMode('simple')}>
              一句话
            </span>
            <span className={`chip ${form.mode === 'custom' ? 'on' : ''}`} onClick={() => onMode('custom')}>
              自定义
            </span>
            <span
              className="chip disabled"
              title="V1.1 上线"
              style={{ opacity: 0.35, cursor: 'not-allowed' }}
              onClick={() => onMode('ref')}
            >
              参考音频
            </span>
            <span
              className="chip disabled"
              title="V1.1 上线"
              style={{ opacity: 0.35, cursor: 'not-allowed' }}
              onClick={() => onMode('hum')}
            >
              哼唱成歌
            </span>
          </div>

          {form.mode === 'simple' ? (
            <>
              <div className="label mt-4">一句话描述</div>
              <textarea
                rows={3}
                className="mt-2"
                maxLength={200}
                placeholder="例：写一首雨夜便利店的华语流行，钢琴伴奏，女声"
                value={form.simplePrompt}
                onChange={(e) => {
                  patchForm({ simplePrompt: e.target.value })
                  markStep(1)
                }}
              />
              <div className="text-[10px] mt-1.5 leading-relaxed" style={{ color: 'var(--dim)' }}>
                歌词与结构将按描述自动生成；也可切到「歌词助手」先写词。
              </div>
            </>
          ) : (
            <InspireBox />
          )}

          {form.mode === 'custom' && (
            <>
              <div className="label mt-4">风格描述</div>
              <textarea
                rows={3}
                className="mt-2"
                maxLength={meta.generation_limits.max_style_prompt}
                value={form.stylePrompt}
                onChange={(e) => {
                  patchForm({ stylePrompt: e.target.value })
                  markStep(1)
                }}
              />
            </>
          )}

          {form.mode === 'custom' && (
            <>
              <div className="label mt-4">
                歌词 <span className="normal-case tracking-normal" style={{ color: 'var(--dim)' }}>（已识别 {tagCount} 段结构标签）</span>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-2 mb-2">
                {meta.structure_tags.map((t) => (
                  <span key={t.tag} className="chip" onClick={() => insertTag(t.tag)}>
                    {t.label}
                  </span>
                ))}
              </div>
              <textarea
                id="lyricBox"
                rows={5}
                maxLength={meta.generation_limits.max_lyrics}
                value={form.lyrics}
                onChange={(e) => patchForm({ lyrics: e.target.value })}
              />
              <button
                className="btn btn-ghost w-full !py-1.5 text-[11px] mt-2"
                onClick={() => {
                  navigate('/lyrics')
                  toast('已切换到歌词助手')
                }}
              >
                在歌词助手中完善 →
              </button>
            </>
          )}

          <div className="label mt-4">参数与模型</div>
          <ParamPanel />

          <button
            id="btnGenerate"
            className="btn btn-acc w-full mt-5 !py-3 text-[13px] font-bold"
            disabled={generating}
            onClick={() => void submitGeneration()}
          >
            {generating ? '生成中…' : `生成 2 个候选 · ${creditCost} 积分`}
          </button>
          <div className="text-[10px] mt-2.5 leading-relaxed" style={{ color: 'var(--dim)' }}>
            付费方案生成内容含商用授权；全程留痕，可在「合规与权利中心」下载授权证书。
          </div>
        </div>

        {/* 中：结果列 */}
        <div className="px-6 py-5 min-h-[560px] overflow-y-auto">
          <div className="flex items-center justify-between">
            <div className="label">候选 / Candidates</div>
            <div className="text-[11px]" style={{ color: 'var(--dim)' }}>
              试听为低码流预览 · 导出 48kHz / 24bit
            </div>
          </div>

          {generating ? (
            <GenProgress task={task} />
          ) : failureMessage ? (
            <div className="mt-3 card p-5" style={{ borderColor: 'var(--bad)' }}>
              <div className="flex items-center gap-3">
                <span className="dot" style={{ background: 'var(--bad)' }}></span>
                <span className="text-[13px] font-semibold" style={{ color: 'var(--bad)' }}>
                  生成失败
                </span>
              </div>
              <div className="text-[12px] mt-3 leading-relaxed" style={{ color: 'var(--muted)' }}>
                {failureMessage}
              </div>
              <div className="flex gap-2 mt-4">
                <button
                  className="btn btn-acc !py-1.5 !px-3 text-[11px] font-bold"
                  onClick={() => void submitGeneration({ simplified: true })}
                >
                  重试（精简提示词）
                </button>
                <button
                  className="btn btn-ghost !py-1.5 !px-3 text-[11px]"
                  onClick={() => void submitGeneration()}
                >
                  原参数重试
                </button>
              </div>
              <div className="text-[10px] mt-3" style={{ color: 'var(--dim)' }}>
                失败任务积分已自动退还；精简重试将把风格描述关键词减半。
              </div>
            </div>
          ) : candidates.length > 0 ? (
            <div className="mt-3 space-y-3">
              {candidates.map((c, i) => (
                <CandidateCard
                  key={c.id}
                  candidate={c}
                  index={i}
                  workTitle={workTitle ?? '未命名作品'}
                  modelLabel={modelLabel}
                />
              ))}
            </div>
          ) : (
            <div
              className="border border-dashed mt-3 py-16 text-center"
              style={{ borderColor: 'var(--line)' }}
            >
              <svg className="mx-auto" width="40" height="40" viewBox="0 0 40 40" fill="none">
                <rect x="4" y="16" width="4" height="12" fill="#2c2c2c" />
                <rect x="12" y="10" width="4" height="24" fill="#2c2c2c" />
                <rect x="20" y="5" width="4" height="30" fill="#00ff2c" />
                <rect x="28" y="12" width="4" height="20" fill="#2c2c2c" />
              </svg>
              <div className="text-[13px] mt-4 font-semibold" style={{ color: 'var(--muted)' }}>
                三步出第一版
              </div>
              <div className="text-[11px] mt-2 leading-relaxed" style={{ color: 'var(--dim)' }}>
                ① 在左侧「灵感指引」点选场景 / 情绪 / 风格
                <br />
                ② 粘贴歌词或点结构标签 → ③ 点「生成 2 个候选」
              </div>
              <button
                className="btn btn-ghost text-[11px] mt-4"
                onClick={() => {
                  randomInspire()
                  toast('已随机填入一组灵感')
                }}
              >
                先来一组随机灵感
              </button>
            </div>
          )}
        </div>

        {/* 右：版本树 */}
        <VersionTree />
      </div>
    </section>
  )
}
