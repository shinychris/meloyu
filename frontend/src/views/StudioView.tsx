import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStudioStore, defaultStylePrompt, defaultLyrics } from '../stores/studio'
import { useMetaStore } from '../stores/meta'
import { useSessionStore } from '../stores/session'
import { toast } from '../stores/toast'
import { countParenMarks, countStructureTags, insertAtCaret } from '../lib/structure'
import { getModelsRuntime } from '../api/models'
import { useT, useI18nStore, type TranslationKey } from '../i18n'
import StepBar from '../components/studio/StepBar'
import InspireBox from '../components/studio/InspireBox'
import ParamPanel from '../components/studio/ParamPanel'
import GenProgress from '../components/studio/GenProgress'
import CandidateCard from '../components/studio/CandidateCard'
import VersionTree from '../components/studio/VersionTree'
import ReferencePanel from '../components/studio/ReferencePanel'
import HumDialog from '../components/studio/HumDialog'
import { PageHeader } from '../components/common/PageHeader'
import { EmptyState } from '../components/common/EmptyState'

const MODE_HINTS: Record<string, TranslationKey> = {
  simple: 'studio.modeHint.simple',
  custom: 'studio.modeHint.custom',
  ref: 'studio.modeHint.ref',
}

/** 创作工作台（原型核心视图：左控制 / 歌词编辑 / 候选结果 / 右版本树）；
 *  歌词编辑区自控制列独立成列，占据原候选列位置，候选列右移一列 */
export default function StudioView() {
  const navigate = useNavigate()
  const t = useT()
  const [songEngine, setSongEngine] = useState('')
  /** FR-4 参考音频面板开合（参考轨挂上后常显，可在面板内移除） */
  const [humOpen, setHumOpen] = useState(false)
  const [refOpen, setRefOpen] = useState(false)
  const lyricBoxRef = useRef<HTMLTextAreaElement | null>(null)
  const form = useStudioStore((s) => s.form)
  const { patchForm, markStep, submitGeneration } = useStudioStore()
  const task = useStudioStore((s) => s.task)
  const candidates = useStudioStore((s) => s.candidates)
  const submitting = useStudioStore((s) => s.submitting)
  const failureMessage = useStudioStore((s) => s.failureMessage)
  const workTitle = useStudioStore((s) => s.workTitle)
  const randomizeInspire = useStudioStore((s) => s.randomizeInspire)
  const meta = useMetaStore((s) => s.meta)
  const referenceTrack = useStudioStore((s) => s.referenceTrack)
  // license（桌面买断）模式：用量纯计量——按钮/失败提示不再出现积分语义（v0.17.0）
  const isLicense = useSessionStore((s) => s.license?.billing_mode === 'license')

  // F-FE-24：价目与型号一律信任 /system/meta（含 stores/meta.ts 的 defaultMeta 兜底），
  // 不再做字面量兜底；模型档位异常缺失时展示文案走 i18n
  const model = meta.models.find((m) => m.value === form.model)
  const creditCost = model?.credit_cost ?? 0
  const modelLabel = model?.label ?? t('studio.view.modelUnknown')
  // F-FE-13：样例态（字段为空）显示当前 locale 的默认样例，切语言自然跟随
  const stylePromptText = form.stylePrompt || defaultStylePrompt()
  const lyricsText = form.lyrics || defaultLyrics()
  const tagCount = countStructureTags(lyricsText)
  const markCount = countParenMarks(lyricsText)
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
    const el = lyricBoxRef.current
    const caret = el?.selectionStart ?? lyricsText.length
    const [next, pos] = insertAtCaret(lyricsText, caret, tag, { block: true })
    patchForm({ lyrics: next })
    markStep(2)
    requestAnimationFrame(() => {
      el?.focus()
      el?.setSelectionRange(pos, pos)
    })
  }

  /** 表演标记：内联插入光标处（音乐编排类整行包裹） */
  const insertMark = (mark: string, group: string) => {
    const el = lyricBoxRef.current
    const caret = el?.selectionStart ?? lyricsText.length
    const [next, pos] = insertAtCaret(lyricsText, caret, mark, { block: group === 'music' })
    patchForm({ lyrics: next })
    markStep(2)
    requestAnimationFrame(() => {
      el?.focus()
      el?.setSelectionRange(pos, pos)
    })
  }

  return (
    <section className="view flex flex-col h-full">
      <PageHeader
        label={t('studio.view.label')}
        title={t('studio.view.headline')}
        actions={
          <div className="flex items-center gap-3 text-xs text-muted">
            <span className="flex items-center gap-2">
              <span className="dot" style={{ background: 'var(--acc)' }}></span>
              {modelLabel} · {t('studio.view.vocalOptimized')}
            </span>
            {songEngine && (
              <span
                className="text-2xs font-bold px-2 py-1 cursor-pointer border border-line bg-bg-2 text-dim"
                title={t('studio.view.songEngineTitle')}
                onClick={() => navigate('/models')}
              >
                {t('studio.view.songEngine', { name: songEngine })}
              </span>
            )}
          </div>
        }
      >
        <StepBar />
      </PageHeader>

      <div
        className={`grid grid-cols-1 rule-t flex-1 min-h-0 ${
          form.mode === 'custom'
            ? 'lg:grid-cols-[300px_1fr_1fr_180px] xl:grid-cols-[360px_1fr_1fr_200px]'
            : 'lg:grid-cols-[300px_1fr_180px] xl:grid-cols-[360px_1fr_200px]'
        }`}
      >
        {/* 左：控制列 */}
        <div className="border-r border-line px-6 py-5 overflow-y-auto">
          <div className="label">{t('studio.mode')}</div>
          <div className="flex gap-1.5 mt-2 flex-wrap">
            <button type="button" className={`chip ${form.mode === 'simple' ? 'on' : ''}`} onClick={() => onMode('simple')}>
              {t('studio.mode.simple')}
            </button>
            <button type="button" className={`chip ${form.mode === 'custom' ? 'on' : ''}`} onClick={() => onMode('custom')}>
              {t('studio.mode.custom')}
            </button>
            <button
              type="button"
              className={`chip ${referenceTrack || refOpen ? 'on' : ''}`}
              title={t('studio.modeHint.ref')}
              onClick={() => onMode('ref')}
            >
              {t('studio.mode.ref')}
              {referenceTrack && (
                <span className="dot ml-1" style={{ background: 'var(--acc)', display: 'inline-block' }}></span>
              )}
            </button>
            <button type="button" className={`chip ${form.humMelody ? 'on' : ''}`} onClick={() => setHumOpen(true)}>
              {t('studio.mode.hum')}
              {form.humMelody && (
                <span className="dot ml-1" style={{ background: 'var(--acc)', display: 'inline-block' }}></span>
              )}
            </button>
          </div>

          {(refOpen || referenceTrack) && (
            <ReferencePanel onClose={() => setRefOpen(false)} />
          )}

          <HumDialog
            open={humOpen}
            onClose={() => setHumOpen(false)}
            onApply={(melody, bpmHint) => {
              patchForm({ humMelody: melody, bpm: bpmHint })
              markStep(1)
            }}
          />

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
              <div className="text-2xs mt-1.5 leading-relaxed text-dim">
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
                value={stylePromptText}
                onChange={(e) => {
                  patchForm({ stylePrompt: e.target.value })
                  markStep(1)
                }}
              />
            </>
          )}

          <div className="label mt-4">{t('studio.param.label')}</div>
          <ParamPanel />

          <button
            id="btnGenerate"
            className="btn btn-acc btn-lg w-full mt-5 font-bold"
            disabled={generating}
            onClick={() => void submitGeneration()}
          >
            {generating
              ? t('studio.generate.generating')
              : t(isLicense ? 'studio.generate.buttonLocal' : 'studio.generate.button', { n: creditCost })}
          </button>
          <div className="text-2xs mt-2.5 leading-relaxed text-dim">
            {t('studio.generate.complianceNote')}
          </div>
        </div>

        {/* 歌词编辑列（自控制列独立，占原候选列位置；custom 模式专属，id=lyricBox 供新手引导定位） */}
        {form.mode === 'custom' && (
          <div className="border-r border-line px-6 py-5 overflow-y-auto">
            <div className="label">
              {t('studio.lyrics.label')}{' '}
              <span className="normal-case tracking-normal text-dim">
                {t('studio.lyrics.tagCount', { n: tagCount })}
                {markCount > 0 ? ` · ${t('studio.lyrics.markCount', { n: markCount })}` : ''}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {meta.structure_tags.map((tg) => (
                <button
                  type="button"
                  key={tg.tag}
                  className="chip"
                  title={tg.desc ?? tg.label}
                  onClick={() => insertTag(tg.tag)}
                >
                  {tg.tag} {tg.label}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap gap-1.5 mt-2 mb-2">
              {(meta.performance_marks ?? []).map((m) => (
                <button
                  type="button"
                  key={m.mark}
                  className="chip"
                  title={t('studio.lyrics.markTitle')}
                  onClick={() => insertMark(m.mark, m.group)}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <textarea
              id="lyricBox"
              ref={lyricBoxRef}
              rows={12}
              maxLength={meta.generation_limits.max_lyrics}
              value={lyricsText}
              onChange={(e) => patchForm({ lyrics: e.target.value })}
            />
            <button
              className="btn btn-ghost btn-sm w-full mt-2"
              onClick={() => {
                navigate('/lyrics')
                toast(t('studio.toast.switchedToLyrics'))
              }}
            >
              {t('studio.lyrics.openAssistant')}
            </button>
          </div>
        )}

        {/* 候选列（歌词编辑列独立后右移一列） */}
        <div className="px-6 py-5 min-h-[560px] overflow-y-auto">
          <div className="flex items-center justify-between">
            <div className="label">{t('studio.candidates.title')}</div>
            <div className="text-xs text-dim">
              {t('studio.candidates.previewNote')}
            </div>
          </div>

          {generating ? (
            <GenProgress task={task} />
          ) : failureMessage ? (
            <div className="mt-3 card p-5" style={{ borderColor: 'var(--bad)' }}>
              <div className="flex items-center gap-3">
                <span className="dot" style={{ background: 'var(--bad)' }}></span>
                <span className="text-base font-semibold text-bad">
                  {t('studio.failure.title')}
                </span>
              </div>
              <div className="text-sm mt-3 leading-relaxed text-muted">
                {failureMessage}
              </div>
              <div className="flex gap-2 mt-4">
                <button
                  className="btn btn-acc btn-sm font-bold"
                  onClick={() => void submitGeneration({ simplified: true })}
                >
                  {t('studio.failure.retrySimplified')}
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => void submitGeneration()}
                >
                  {t('studio.failure.retryOriginal')}
                </button>
              </div>
              <div className="text-2xs mt-3 text-dim">
                {t(isLicense ? 'studio.failure.noteLocal' : 'studio.failure.note')}
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
            <EmptyState
              className="mt-3"
              title={t('studio.empty.title')}
              hint={
                <>
                  {t('studio.empty.step1')}
                  <br />
                  {t('studio.empty.step2')}
                </>
              }
              actionLabel={t('studio.empty.random')}
              onAction={() => {
                randomizeInspire()
                toast(t('studio.toast.randomInspired'))
              }}
            />
          )}
        </div>

        {/* 右：版本树 */}
        <VersionTree />
      </div>
    </section>
  )
}
