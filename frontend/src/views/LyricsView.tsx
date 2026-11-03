import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { completeTags, generateLyrics, polishLyrics, rhymeCheck } from '../api/lyrics'
import { getModelsRuntime } from '../api/models'
import type { CompleteTagsResult, LyricsGenerateResult, RhymeCheckResult } from '../types/api'
import { useStudioStore } from '../stores/studio'
import { toast } from '../stores/toast'
import { useT, t as tt, useI18nStore, getLocale } from '../i18n'
import { lyricsZh } from '../i18n/zh/lyrics'
import { lyricsEn } from '../i18n/en/lyrics'
import { detectSectionAtCaret, insertAtCaret, parseLyricsStructure } from '../lib/structure'
import { sectionLabel } from '../lib/format'
import { useMetaStore } from '../stores/meta'
import AnalysisPanel from '../components/lyrics/AnalysisPanel'
import { PageHeader } from '../components/common/PageHeader'

const DRAFT_KEY = 'meloyu:lyric-draft:v1' //  R2：草稿由前端 localStorage 承载

/** 全部语言的默认样例文本：判定编辑器里是否仍是「未被改动的样例」 */
export const SAMPLE_TEXTS = new Set([lyricsZh['lyrics.defaultLyrics'], lyricsEn['lyrics.defaultLyrics']])

/** 草稿解析：用户内容优先；历史草稿若只是旧语言样例则归入样例态（返回
 *  null，v0.12.3——显示值由当前 locale 的样例派生，切换语言自然跟随） */
export function resolveDraftText(saved: string | null): string | null {
  return saved != null && !SAMPLE_TEXTS.has(saved) ? saved : null
}

/** 编辑器初始示例歌词（按当前 locale） */
function defaultLyrics(): string {
  return tt('lyrics.defaultLyrics')
}

/** 启动草稿：用户编辑过的内容，或 null（编辑器显示默认样例态） */
function loadUserDraft(): string | null {
  try {
    return resolveDraftText(localStorage.getItem(DRAFT_KEY))
  } catch {
    return null
  }
}

interface ChangeEntry {
  line_no: number
  before: string
  after: string
}

/** 歌词助手：AI 生成 / 润色选中段 / 押韵重音检查 / 标签补全（四接口全接） */
export default function LyricsView() {
  const t = useT()
  /** userText=null 表示样例态：显示值派生自当前 locale 的样例，语言切换自动跟随 */
  const [userText, setUserText] = useState<string | null>(loadUserDraft)
  const text = userText ?? defaultLyrics()
  const [theme, setTheme] = useState('')
  const [mood, setMood] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [gen, setGen] = useState<LyricsGenerateResult | null>(null)
  const [rhyme, setRhyme] = useState<RhymeCheckResult | null>(null)
  const [tagInfo, setTagInfo] = useState<CompleteTagsResult | null>(null)
  const [changes, setChanges] = useState<ChangeEntry[]>([])
  const [engine, setEngine] = useState('')
  const editorRef = useRef<HTMLTextAreaElement | null>(null)
  const navigate = useNavigate()
  const setLyricsFromAssistant = useStudioStore((s) => s.setLyricsFromAssistant)
  const meta = useMetaStore((s) => s.meta)
  const loadMeta = useMetaStore((s) => s.load)
  useEffect(() => {
    void loadMeta()
  }, [loadMeta])
  const vocalMarks = (meta.performance_marks ?? []).filter((m) => m.group === 'vocal')
  const musicMarks = (meta.performance_marks ?? []).filter((m) => m.group === 'music')
  // F-04：结构面板随编辑内容实时解析（镜像后端 parse_lyrics 语义），
  // 不再展示上一次生成响应的段落快照
  const structure = useMemo(() => parseLyricsStructure(text), [text])

  // 草稿持久化：只有真正编辑过的内容才落 localStorage（样例态不落盘，
  // 避免旧语言样例锁死语言切换；顺带清掉历史残留）
  useEffect(() => {
    try {
      if (userText == null) localStorage.removeItem(DRAFT_KEY)
      else localStorage.setItem(DRAFT_KEY, userText)
    } catch {
      /* ignore */
    }
  }, [userText])

  // V1.2：显示当前歌词引擎（模型中心可切换）；依赖 locale——后端按 Accept-Language 本地化
  const locale = useI18nStore((s) => s.locale)
  useEffect(() => {
    getModelsRuntime()
      .then((rt) => setEngine(rt.engine))
      .catch(() => {})
  }, [locale])

  const run = async (key: string, fn: () => Promise<void>) => {
    if (busy) return
    setBusy(key)
    try {
      await fn()
    } catch {
      /* 拦截器已 toast（42201 敏感词等） */
    } finally {
      setBusy(null)
    }
  }

  const onGenerate = () =>
    run('gen', async () => {
      if (!theme.trim()) {
        toast(t('lyrics.toast.themeRequired'), 'warn')
        return
      }
      // ：语言跟随界面 locale（zh 用户默认中文；英文界面不再产出中文歌词）
      const res = await generateLyrics({ theme: theme.trim(), mood: mood.trim() || null, language: getLocale() === 'en' ? 'en' : 'zh' })
      setGen(res)
      setRhyme(null)
      setChanges([])
      setUserText(res.lyrics)
      toast(t('lyrics.toast.generated', { engine: res.engine || engine }))
      useStudioStore.getState().logOp(t('lyrics.log.generated'))
    })

  const onPolish = () =>
    run('polish', async () => {
      if (!text.trim()) {
        toast(t('lyrics.toast.empty'), 'warn')
        return
      }
      const caret = editorRef.current?.selectionStart ?? text.length
      const section = detectSectionAtCaret(text, caret)
      const res = await polishLyrics({ lyrics: text, ...(section ? { target_section: section } : {}) })
      setChanges(res.changes)
      setUserText(res.lyrics)
      toast(
        section
          ? t('lyrics.toast.polishedSection', { section: sectionLabel(section), n: res.changes.length })
          : t('lyrics.toast.polishedAll', { n: res.changes.length }),
      )
    })

  const onRhyme = () =>
    run('rhyme', async () => {
      if (!text.trim()) {
        toast(t('lyrics.toast.empty'), 'warn')
        return
      }
      const res = await rhymeCheck(text)
      setRhyme(res)
      toast(
        res.off_rhyme_count > 0
          ? t('lyrics.toast.rhymeOff', { n: res.off_rhyme_count, group: res.main_rhyme_group })
          : t('lyrics.toast.rhymeAll', { group: res.main_rhyme_group }),
      )
    })

  const onTags = () =>
    run('tags', async () => {
      if (!text.trim()) {
        toast(t('lyrics.toast.empty'), 'warn')
        return
      }
      const res = await completeTags(text)
      setTagInfo(res)
      setUserText(res.lyrics)
      toast(res.inferred ? t('lyrics.toast.tagsInferred') : t('lyrics.toast.tagsNormalized'))
    })

  /** 在编辑器光标处插入片段（段落标签整行包裹 / 表演标记内联） */
  const insertSnippet = (snippet: string, block = false) => {
    const el = editorRef.current
    const caret = el?.selectionStart ?? text.length
    const [next, pos] = insertAtCaret(text, caret, snippet, { block })
    setUserText(next)
    requestAnimationFrame(() => {
      el?.focus()
      el?.setSelectionRange(pos, pos)
    })
  }

  return (
    <section className="view flex flex-col h-full">
      <PageHeader
        label={t('lyrics.header.label')}
        title={t('lyrics.header.headline')}
        actions={
          engine ? (
            <span
              className="text-2xs font-bold px-2 py-1 cursor-pointer border border-line bg-bg-2 text-muted"
              title={t('lyrics.engine.title')}
              onClick={() => navigate('/models')}
            >
              {t('lyrics.engine.badge', { engine })}
            </span>
          ) : undefined
        }
      />
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] xl:grid-cols-[1fr_300px] rule-t flex-1 min-h-0">
        <div className="px-8 py-5 border-r border-line overflow-y-auto">
          <div className="mb-3">
            <div className="text-2xs mb-1 text-dim">{t('lyrics.theme.label')}</div>
            <textarea
              rows={3}
              maxLength={600}
              placeholder={t('lyrics.theme.placeholder')}
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
            />
          </div>
          <div className="w-1/2 pr-1 mb-3">
            <div className="text-2xs mb-1 text-dim">{t('lyrics.mood.label')}</div>
            <input
              type="text"
              maxLength={20}
              placeholder={t('lyrics.mood.placeholder')}
              value={mood}
              onChange={(e) => setMood(e.target.value)}
            />
          </div>
          <div className="flex gap-2 mb-3 flex-wrap">
            <button className="btn btn-ghost btn-sm" disabled={busy !== null} onClick={onGenerate}
              title={engine ? t('lyrics.action.generateTitle') : undefined}>
              {busy === 'gen' ? t('lyrics.action.generating') : t('lyrics.action.generate')}
            </button>
            <button className="btn btn-ghost btn-sm" disabled={busy !== null} onClick={onPolish}>
              {busy === 'polish' ? t('lyrics.action.polishing') : t('lyrics.action.polish')}
            </button>
            <button className="btn btn-ghost btn-sm" disabled={busy !== null} onClick={onRhyme}>
              {busy === 'rhyme' ? t('lyrics.action.checking') : t('lyrics.action.rhyme')}
            </button>
            <button className="btn btn-ghost btn-sm" disabled={busy !== null} onClick={onTags}>
              {t('lyrics.action.tags')}
            </button>
            <button
              className="btn btn-ghost btn-sm"
              style={{ color: 'var(--acc)', borderColor: 'var(--acc)' }}
              onClick={() => {
                setLyricsFromAssistant(text)
                toast(t('lyrics.toast.applied'))
              }}
            >
              {t('lyrics.action.apply')}
            </button>
          </div>
          <div className="mt-2 mb-3">
            <div className="text-2xs mb-1.5 text-dim">{t('lyrics.chips.tags')}</div>
            <div className="flex gap-1.5 flex-wrap">
              {meta.structure_tags.map((tg) => (
                <button
                  type="button"
                  key={tg.tag}
                  className="chip"
                  title={tg.desc ?? tg.label}
                  onClick={() => insertSnippet(tg.tag, true)}
                >
                  {tg.tag} {tg.label}
                </button>
              ))}
            </div>
          </div>
          <div className="mb-3">
            <div className="text-2xs mb-1.5 text-dim">
              {t('lyrics.chips.marks')}
              <span className="ml-2" title={t('lyrics.chips.marksHint')}>ⓘ</span>
            </div>
            <div className="flex gap-1.5 flex-wrap">
              {vocalMarks.map((m) => (
                <button type="button" key={m.mark} className="chip" onClick={() => insertSnippet(m.mark)}>
                  {m.label}
                </button>
              ))}
            </div>
            <div className="flex gap-1.5 flex-wrap mt-1.5">
              {musicMarks.map((m) => (
                <button type="button" key={m.mark} className="chip" onClick={() => insertSnippet(m.mark, true)}>
                  {m.label}
                </button>
              ))}
            </div>
          </div>
          <textarea
            ref={editorRef}
            rows={16}
            maxLength={4000}
            value={text}
            onChange={(e) => setUserText(e.target.value)}
          />
          {gen && gen.alternatives.length > 0 && (
            <div className="mt-3">
              <div className="label mb-2">{t('lyrics.alternatives')}</div>
              <div className="flex gap-1.5 flex-wrap">
                {gen.alternatives.map((alt, i) => (
                  <button
                    type="button"
                    key={i}
                    className="chip"
                    onClick={() => {
                      setUserText(alt.lyrics)
                      toast(t('lyrics.toast.altLoaded', { n: i + 1 }))
                    }}
                  >
                    {t('lyrics.alternative', { n: i + 1 })}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <AnalysisPanel
          structure={structure}
          rhyme={rhyme}
          tagInfo={tagInfo}
          changes={changes}
          onBackStudio={() => {
            navigate('/studio')
            toast(t('lyrics.toast.backStudio'))
          }}
        />
      </div>
    </section>
  )
}
