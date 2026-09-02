import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { completeTags, generateLyrics, polishLyrics, rhymeCheck } from '../api/lyrics'
import { getModelsRuntime } from '../api/models'
import type { CompleteTagsResult, LyricsGenerateResult, RhymeCheckResult } from '../types/api'
import { useStudioStore } from '../stores/studio'
import { toast } from '../stores/toast'
import { useT, t as tt, useI18nStore } from '../i18n'
import { detectSectionAtCaret } from '../lib/structure'
import { sectionLabel } from '../lib/format'
import AnalysisPanel from '../components/lyrics/AnalysisPanel'

const DRAFT_KEY = 'meloyu:lyric-draft:v1' // 契约 §14 R2：草稿由前端 localStorage 承载

/** 本地规则引擎判定（后端 engine 字段按 Accept-Language 本地化，中英都要匹配） */
const LOCAL_RULE_RE = /本地规则|local rule/i

/** 编辑器初始示例歌词（按当前 locale；用户草稿优先） */
function defaultLyrics(): string {
  return tt('lyrics.defaultLyrics')
}

function loadDraft(): string {
  try {
    return localStorage.getItem(DRAFT_KEY) ?? defaultLyrics()
  } catch {
    return defaultLyrics()
  }
}

interface ChangeEntry {
  line_no: number
  before: string
  after: string
}

/** 歌词助手：AI 生成 / 润色选中段 / 押韵重音检查 / 标签补全（契约 §6 四接口全接） */
export default function LyricsView() {
  const t = useT()
  const [text, setText] = useState<string>(loadDraft)
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

  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_KEY, text)
    } catch {
      /* ignore */
    }
  }, [text])

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
      const res = await generateLyrics({ theme: theme.trim(), mood: mood.trim() || null, language: 'zh' })
      setGen(res)
      setRhyme(null)
      setChanges([])
      setText(res.lyrics)
      if (res.fallback && res.fallback_reason) {
        toast(t('lyrics.toast.fallback', { reason: res.fallback_reason }), 'warn')
      } else {
        toast(t('lyrics.toast.generated', { engine: res.engine || engine }))
      }
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
      setText(res.lyrics)
      if (res.fallback && res.fallback_reason) {
        toast(t('lyrics.toast.fallback', { reason: res.fallback_reason }), 'warn')
      } else {
        toast(
          section
            ? t('lyrics.toast.polishedSection', { section: sectionLabel(section), n: res.changes.length })
            : t('lyrics.toast.polishedAll', { n: res.changes.length }),
        )
      }
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
      setText(res.lyrics)
      toast(res.inferred ? t('lyrics.toast.tagsInferred') : t('lyrics.toast.tagsNormalized'))
    })

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4">
        <div className="label">{t('lyrics.header.label')}</div>
        <div className="flex items-end justify-between">
          <h1 className="text-[28px] font-extrabold tracking-tight mt-1">{t('lyrics.header.headline')}</h1>
          {engine && (
            <span
              className="text-[10px] font-bold px-2 py-1 cursor-pointer"
              style={{ background: 'var(--bg2)', border: '1px solid var(--line)', color: 'var(--dim)' }}
              title={t('lyrics.engine.title')}
              onClick={() => navigate('/models')}
            >
              {t('lyrics.engine.badge', { engine })}
            </span>
          )}
        </div>
      </header>
      <div className="grid grid-cols-[1fr_300px] rule-t flex-1 min-h-0">
        <div className="px-8 py-5 border-r overflow-y-auto" style={{ borderColor: 'var(--line)' }}>
          <div className="grid grid-cols-2 gap-2.5 mb-3">
            <div>
              <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>{t('lyrics.theme.label')}</div>
              <input
                type="text"
                maxLength={100}
                placeholder={t('lyrics.theme.placeholder')}
                value={theme}
                onChange={(e) => setTheme(e.target.value)}
              />
            </div>
            <div>
              <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>{t('lyrics.mood.label')}</div>
              <input
                type="text"
                maxLength={20}
                placeholder={t('lyrics.mood.placeholder')}
                value={mood}
                onChange={(e) => setMood(e.target.value)}
              />
            </div>
          </div>
          <div className="flex gap-2 mb-3 flex-wrap">
            <button className="btn btn-ghost text-[11px]" disabled={busy !== null} onClick={onGenerate}
              title={engine && !LOCAL_RULE_RE.test(engine) ? t('lyrics.action.generateTitle') : undefined}>
              {busy === 'gen'
                ? engine && !LOCAL_RULE_RE.test(engine) ? t('lyrics.action.generatingLLM') : t('lyrics.action.generating')
                : t('lyrics.action.generate')}
            </button>
            <button className="btn btn-ghost text-[11px]" disabled={busy !== null} onClick={onPolish}>
              {busy === 'polish' ? t('lyrics.action.polishing') : t('lyrics.action.polish')}
            </button>
            <button className="btn btn-ghost text-[11px]" disabled={busy !== null} onClick={onRhyme}>
              {busy === 'rhyme' ? t('lyrics.action.checking') : t('lyrics.action.rhyme')}
            </button>
            <button className="btn btn-ghost text-[11px]" disabled={busy !== null} onClick={onTags}>
              {t('lyrics.action.tags')}
            </button>
            <button className="btn btn-ghost text-[11px]" onClick={() => toast(t('lyrics.action.bridgeSoon'), 'warn')}>
              {t('lyrics.action.bridge')}
            </button>
            <button
              className="btn btn-ghost text-[11px]"
              style={{ color: 'var(--acc)', borderColor: 'var(--acc)' }}
              onClick={() => {
                setLyricsFromAssistant(text)
                toast(t('lyrics.toast.applied'))
              }}
            >
              {t('lyrics.action.apply')}
            </button>
          </div>
          <textarea
            ref={editorRef}
            rows={16}
            maxLength={4000}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          {gen && gen.alternatives.length > 0 && (
            <div className="mt-3">
              <div className="label mb-2">{t('lyrics.alternatives')}</div>
              <div className="flex gap-1.5 flex-wrap">
                {gen.alternatives.map((alt, i) => (
                  <span
                    key={i}
                    className="chip"
                    onClick={() => {
                      setText(alt.lyrics)
                      toast(t('lyrics.toast.altLoaded', { n: i + 1 }))
                    }}
                  >
                    {t('lyrics.alternative', { n: i + 1 })}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        <AnalysisPanel
          gen={gen}
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
