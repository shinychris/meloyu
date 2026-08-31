import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { completeTags, generateLyrics, polishLyrics, rhymeCheck } from '../api/lyrics'
import { getModelsRuntime } from '../api/models'
import type { CompleteTagsResult, LyricsGenerateResult, RhymeCheckResult } from '../types/api'
import { useStudioStore } from '../stores/studio'
import { toast } from '../stores/toast'
import { detectSectionAtCaret } from '../lib/structure'
import { SECTION_ZH } from '../lib/format'
import AnalysisPanel from '../components/lyrics/AnalysisPanel'

const DRAFT_KEY = 'meloyu:lyric-draft:v1' // 契约 §14 R2：草稿由前端 localStorage 承载

const DEFAULT_LYRICS = `[Verse]
雨停在凌晨三点的窗台
霓虹把影子拉得好白
便利店的灯还亮着
像没说完的对白

[Pre-Chorus]
我数着屋檐滴落的节拍
一下一下都是等待

[Chorus]
我们把未来说得太轻
像风穿过无人的街心
承诺若只剩回音
至少今夜还有雨声`

function loadDraft(): string {
  try {
    return localStorage.getItem(DRAFT_KEY) ?? DEFAULT_LYRICS
  } catch {
    return DEFAULT_LYRICS
  }
}

interface ChangeEntry {
  line_no: number
  before: string
  after: string
}

/** 歌词助手：AI 生成 / 润色选中段 / 押韵重音检查 / 标签补全（契约 §6 四接口全接） */
export default function LyricsView() {
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

  // V1.2：显示当前歌词引擎（模型中心可切换）
  useEffect(() => {
    getModelsRuntime()
      .then((rt) => setEngine(rt.engine))
      .catch(() => {})
  }, [])

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
        toast('先填一个主题或一句话（1~100 字）', 'warn')
        return
      }
      const res = await generateLyrics({ theme: theme.trim(), mood: mood.trim() || null, language: 'zh' })
      setGen(res)
      setRhyme(null)
      setChanges([])
      setText(res.lyrics)
      if (res.fallback && res.fallback_reason) {
        toast(`引擎不可用已回退本地规则：${res.fallback_reason}`, 'warn')
      } else {
        toast(`AI 已生成歌词草稿（${res.engine || engine}），可继续润色`)
      }
      useStudioStore.getState().logOp('歌词助手：AI 生成草稿')
    })

  const onPolish = () =>
    run('polish', async () => {
      if (!text.trim()) {
        toast('歌词为空', 'warn')
        return
      }
      const caret = editorRef.current?.selectionStart ?? text.length
      const section = detectSectionAtCaret(text, caret)
      const res = await polishLyrics({ lyrics: text, ...(section ? { target_section: section } : {}) })
      setChanges(res.changes)
      setText(res.lyrics)
      if (res.fallback && res.fallback_reason) {
        toast(`引擎不可用已回退本地规则：${res.fallback_reason}`, 'warn')
      } else {
        toast(
          section
            ? `已润色${SECTION_ZH[section]}（${res.changes.length} 处修改）`
            : `已润色全文（${res.changes.length} 处修改）`,
        )
      }
    })

  const onRhyme = () =>
    run('rhyme', async () => {
      if (!text.trim()) {
        toast('歌词为空', 'warn')
        return
      }
      const res = await rhymeCheck(text)
      setRhyme(res)
      toast(
        res.off_rhyme_count > 0
          ? `检查完成：${res.off_rhyme_count} 处出韵，主韵 ${res.main_rhyme_group}`
          : `检查完成：全部押韵（主韵 ${res.main_rhyme_group}）`,
      )
    })

  const onTags = () =>
    run('tags', async () => {
      if (!text.trim()) {
        toast('歌词为空', 'warn')
        return
      }
      const res = await completeTags(text)
      setTagInfo(res)
      setText(res.lyrics)
      toast(res.inferred ? '原歌词无标签，已按模板补全结构' : '已识别并规范化结构标签')
    })

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4">
        <div className="label">Lyrics / 歌词助手</div>
        <div className="flex items-end justify-between">
          <h1 className="text-[28px] font-extrabold tracking-tight mt-1">写词，并与旋律对齐</h1>
          {engine && (
            <span
              className="text-[10px] font-bold px-2 py-1 cursor-pointer"
              style={{ background: 'var(--bg2)', border: '1px solid var(--line)', color: 'var(--dim)' }}
              title="在模型中心切换 AI 引擎（本地规则 / 本地开源模型 / 外部 API）"
              onClick={() => navigate('/models')}
            >
              引擎：{engine} ⇄
            </span>
          )}
        </div>
      </header>
      <div className="grid grid-cols-[1fr_300px] rule-t flex-1 min-h-0">
        <div className="px-8 py-5 border-r overflow-y-auto" style={{ borderColor: 'var(--line)' }}>
          <div className="grid grid-cols-2 gap-2.5 mb-3">
            <div>
              <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>主题 / 一句话（生成用，必填）</div>
              <input
                type="text"
                maxLength={100}
                placeholder="例：雨夜便利店等待"
                value={theme}
                onChange={(e) => setTheme(e.target.value)}
              />
            </div>
            <div>
              <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>情绪（可选，如：忧郁 / 热血）</div>
              <input
                type="text"
                maxLength={20}
                placeholder="命中意象库"
                value={mood}
                onChange={(e) => setMood(e.target.value)}
              />
            </div>
          </div>
          <div className="flex gap-2 mb-3 flex-wrap">
            <button className="btn btn-ghost text-[11px]" disabled={busy !== null} onClick={onGenerate}
              title={engine && !engine.includes('本地规则') ? 'LLM 引擎生成中，视模型 10s~3min' : undefined}>
              {busy === 'gen'
                ? engine && !engine.includes('本地规则') ? 'AI 生成中（最长约 3 分钟）…' : '生成中…'
                : 'AI 生成歌词'}
            </button>
            <button className="btn btn-ghost text-[11px]" disabled={busy !== null} onClick={onPolish}>
              {busy === 'polish' ? '润色中…' : '润色选中段'}
            </button>
            <button className="btn btn-ghost text-[11px]" disabled={busy !== null} onClick={onRhyme}>
              {busy === 'rhyme' ? '检查中…' : '押韵 / 重音检查'}
            </button>
            <button className="btn btn-ghost text-[11px]" disabled={busy !== null} onClick={onTags}>
              补全结构标签
            </button>
            <button className="btn btn-ghost text-[11px]" onClick={() => toast('续写桥段将在 V1.1 上线', 'warn')}>
              续写桥段
            </button>
            <button
              className="btn btn-ghost text-[11px]"
              style={{ color: 'var(--acc)', borderColor: 'var(--acc)' }}
              onClick={() => {
                setLyricsFromAssistant(text)
                toast('已应用到创作工作台的歌词框')
              }}
            >
              应用到工作台 →
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
              <div className="label mb-2">备选版本</div>
              <div className="flex gap-1.5 flex-wrap">
                {gen.alternatives.map((alt, i) => (
                  <span
                    key={i}
                    className="chip"
                    onClick={() => {
                      setText(alt.lyrics)
                      toast(`已载入备选 ${i + 1}`)
                    }}
                  >
                    备选 {i + 1}
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
            toast('已回到创作工作台')
          }}
        />
      </div>
    </section>
  )
}
