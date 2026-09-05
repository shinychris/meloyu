import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStudioStore } from '../stores/studio'
import { useMetaStore } from '../stores/meta'
import { toast } from '../stores/toast'
import { countStructureTags } from '../lib/structure'
import { getModelsRuntime } from '../api/models'
import { useT, useI18nStore, type TranslationKey } from '../i18n'
import StepBar from '../components/studio/StepBar'
import InspireBox from '../components/studio/InspireBox'
import ParamPanel from '../components/studio/ParamPanel'
import GenProgress from '../components/studio/GenProgress'
import CandidateCard from '../components/studio/CandidateCard'
import VersionTree from '../components/studio/VersionTree'
import ReferencePanel from '../components/studio/ReferencePanel'

const MODE_HINTS: Record<string, TranslationKey> = {
  simple: 'studio.modeHint.simple',
  custom: 'studio.modeHint.custom',
  ref: 'studio.modeHint.ref',
}

/** 创作工作台（原型核心视图：左控制 / 中结果 / 右版本树） */
export default function StudioView() {
  const navigate = useNavigate()
  const t = useT()
  const [songEngine, setSongEngine] = useState('')
  /** FR-4 参考音频面板开合（参考轨挂上后常显，可在面板内移除） */
  const [refOpen, setRefOpen] = useState(false)
  const form = useStudioStore((s) => s.form)
  const { patchForm, markStep, submitGeneration } = useStudioStore()
  const task = useStudioStore((s) => s.task)
  const candidates = useStudioStore((s) => s.candidates)
  const submitting = useStudioStore((s) => s.submitting)
  const failureMessage = useStudioStore((s) => s.failureMessage)
  const workTitle = useStudioStore((s) => s.workTitle)
  const meta = useMetaStore((s) => s.meta)
  const referenceTrack = useStudioStore((s) => s.referenceTrack)

  const creditCost = meta.models.find((m) => m.value === form.model)?.credit_cost ?? 12
  const modelLabel = meta.models.find((m) => m.value === form.model)?.label ?? 'V1 Pro'
  const tagCount = countStructureTags(form.lyrics)
  const generating =
    submitting || (task != null && (task.status === 'queued' || task.status === 'running'))

  // V1.3：显示当前歌曲引擎（模型中心可切换：本地合成 / 外部歌曲 API）；
  // 依赖 locale——后端按 Accept-Language 返回本地化引擎名，切语言后重拉
  const locale = useI18nStore((s) => s.locale)
  useEffect(() => {
    getModelsRuntime()
      .then((rt) => setSongEngine(rt.song_engine))
      .catch(() => {})
  }, [locale])

  const onMode = (mode: string) => {
    if (mode === 'ref') {
      setRefOpen((v) => !v)
      toast(t(MODE_HINTS.ref))
      return
    }
    patchForm({ mode: mode as typeof form.mode })
    markStep(1)
    toast(t(MODE_HINTS[mode]))
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
      t('studio.log.inspire', {
        detail: [next.genre, next.mood, next.inst, next.scene].filter(Boolean).join(' / '),
      }),
    )
  }

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4">
        <div className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <div className="label">{t('studio.view.label')}</div>
            <h1 className="text-[28px] font-extrabold tracking-tight mt-1">{t('studio.view.headline')}</h1>
          </div>
          <div className="flex items-center gap-3 text-[11px]" style={{ color: 'var(--muted)' }}>
            <span className="flex items-center gap-2">
              <span className="dot" style={{ background: 'var(--acc)' }}></span>
              {modelLabel} · {t('studio.view.vocalOptimized')}
            </span>
            {songEngine && (
              <span
                className="text-[10px] font-bold px-2 py-1 cursor-pointer"
                style={{ background: 'var(--bg2)', border: '1px solid var(--line)', color: 'var(--dim)' }}
                title={t('studio.view.songEngineTitle')}
                onClick={() => navigate('/models')}
              >
                {t('studio.view.songEngine', { name: songEngine })}
              </span>
            )}
          </div>
        </div>
        <StepBar />
      </header>

      <div className="grid grid-cols-[360px_1fr_200px] rule-t flex-1 min-h-0">
        {/* 左：控制列 */}
        <div className="border-r px-6 py-5 overflow-y-auto" style={{ borderColor: 'var(--line)' }}>
          <div className="label">{t('studio.mode')}</div>
          <div className="flex gap-1.5 mt-2 flex-wrap">
            <span className={`chip ${form.mode === 'simple' ? 'on' : ''}`} onClick={() => onMode('simple')}>
              {t('studio.mode.simple')}
            </span>
            <span className={`chip ${form.mode === 'custom' ? 'on' : ''}`} onClick={() => onMode('custom')}>
              {t('studio.mode.custom')}
            </span>
            <span
              className={`chip ${referenceTrack || refOpen ? 'on' : ''}`}
              title={t('studio.modeHint.ref')}
              onClick={() => onMode('ref')}
            >
              {t('studio.mode.ref')}
              {referenceTrack && (
                <span className="dot ml-1" style={{ background: 'var(--acc)', display: 'inline-block' }}></span>
              )}
            </span>
            <span
              className="chip disabled"
              title={t('studio.mode.comingSoon')}
              style={{ opacity: 0.35, cursor: 'not-allowed' }}
            >
              {t('studio.mode.hum')}
            </span>
          </div>

          {(refOpen || referenceTrack) && (
            <ReferencePanel onClose={() => setRefOpen(false)} />
          )}

          {form.mode === 'simple' ? (
            <>
              <div className="label mt-4">{t('studio.simple.label')}</div>
              <textarea
                rows={3}
                className="mt-2"
                maxLength={200}
                placeholder={t('studio.simple.placeholder')}
                value={form.simplePrompt}
                onChange={(e) => {
                  patchForm({ simplePrompt: e.target.value })
                  markStep(1)
                }}
              />
              <div className="text-[10px] mt-1.5 leading-relaxed" style={{ color: 'var(--dim)' }}>
                {t('studio.simple.hint')}
              </div>
            </>
          ) : (
            <InspireBox />
          )}

          {form.mode === 'custom' && (
            <>
              <div className="label mt-4">{t('studio.style.label')}</div>
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
                {t('studio.lyrics.label')} <span className="normal-case tracking-normal" style={{ color: 'var(--dim)' }}>{t('studio.lyrics.tagCount', { n: tagCount })}</span>
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
                  toast(t('studio.toast.switchedToLyrics'))
                }}
              >
                {t('studio.lyrics.openAssistant')}
              </button>
            </>
          )}

          <div className="label mt-4">{t('studio.param.label')}</div>
          <ParamPanel />

          <button
            id="btnGenerate"
            className="btn btn-acc w-full mt-5 !py-3 text-[13px] font-bold"
            disabled={generating}
            onClick={() => void submitGeneration()}
          >
            {generating ? t('studio.generate.generating') : t('studio.generate.button', { n: creditCost })}
          </button>
          <div className="text-[10px] mt-2.5 leading-relaxed" style={{ color: 'var(--dim)' }}>
            {t('studio.generate.complianceNote')}
          </div>
        </div>

        {/* 中：结果列 */}
        <div className="px-6 py-5 min-h-[560px] overflow-y-auto">
          <div className="flex items-center justify-between">
            <div className="label">{t('studio.candidates.title')}</div>
            <div className="text-[11px]" style={{ color: 'var(--dim)' }}>
              {t('studio.candidates.previewNote')}
            </div>
          </div>

          {generating ? (
            <GenProgress task={task} />
          ) : failureMessage ? (
            <div className="mt-3 card p-5" style={{ borderColor: 'var(--bad)' }}>
              <div className="flex items-center gap-3">
                <span className="dot" style={{ background: 'var(--bad)' }}></span>
                <span className="text-[13px] font-semibold" style={{ color: 'var(--bad)' }}>
                  {t('studio.failure.title')}
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
                  {t('studio.failure.retrySimplified')}
                </button>
                <button
                  className="btn btn-ghost !py-1.5 !px-3 text-[11px]"
                  onClick={() => void submitGeneration()}
                >
                  {t('studio.failure.retryOriginal')}
                </button>
              </div>
              <div className="text-[10px] mt-3" style={{ color: 'var(--dim)' }}>
                {t('studio.failure.note')}
              </div>
            </div>
          ) : candidates.length > 0 ? (
            <div className="mt-3 space-y-3">
              {candidates.map((c, i) => (
                <CandidateCard
                  key={c.id}
                  candidate={c}
                  index={i}
                  workTitle={workTitle ?? t('studio.untitled')}
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
                {t('studio.empty.title')}
              </div>
              <div className="text-[11px] mt-2 leading-relaxed" style={{ color: 'var(--dim)' }}>
                {t('studio.empty.step1')}
                <br />
                {t('studio.empty.step2')}
              </div>
              <button
                className="btn btn-ghost text-[11px] mt-4"
                onClick={() => {
                  randomInspire()
                  toast(t('studio.toast.randomInspired'))
                }}
              >
                {t('studio.empty.random')}
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
