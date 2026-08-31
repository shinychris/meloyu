import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import type { Candidate, VersionTreeNode, Work } from '../types/api'
import { getWork, getVersionTree, patchWork } from '../api/works'
import { adoptCandidate, listCandidates as fetchCandidates } from '../api/generation'
import { usePlayerStore } from '../stores/player'
import { toast } from '../stores/toast'
import { formatDuration, keyLabel, SECTION_LABEL, versionSourceLabel } from '../lib/format'
import ExportPanel from '../components/work/ExportPanel'

function depthOf(nodes: VersionTreeNode[], node: VersionTreeNode): number {
  const map = new Map(nodes.map((n) => [n.id, n]))
  let depth = 0
  let cur: VersionTreeNode | undefined = node
  while (cur?.parent_version_id) {
    cur = map.get(cur.parent_version_id)
    depth++
    if (depth > 20) break
  }
  return depth
}

/** 作品详情：版本树 + 候选列表（试听/采用）+ 导出与证书 */
export default function WorkDetailView() {
  const { workId } = useParams<{ workId: string }>()
  const navigate = useNavigate()
  const [work, setWork] = useState<Work | null>(null)
  const [nodes, setNodes] = useState<VersionTreeNode[]>([])
  const [currentVersionId, setCurrentVersionId] = useState<string | null>(null)
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [loading, setLoading] = useState(true)
  /** 标题/标签内联编辑（PATCH /works/{id}，契约 §7.3） */
  const [editing, setEditing] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [tagsDraft, setTagsDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const playTrack = usePlayerStore((s) => s.playTrack)

  const loadCandidates = useCallback(async (versionId: string) => {
    try {
      const res = await fetchCandidates(versionId)
      setCandidates(res.items)
    } catch {
      setCandidates([])
    }
  }, [])

  useEffect(() => {
    if (!workId) return
    let alive = true
    setLoading(true)
    void (async () => {
      try {
        const [w, tree] = await Promise.all([getWork(workId), getVersionTree(workId)])
        if (!alive) return
        setWork(w)
        setNodes(
          [...tree.nodes].sort(
            (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
          ),
        )
        setCurrentVersionId(tree.current_version_id)
        const initial = tree.current_version_id
        setSelectedVersionId(initial)
        if (initial) void loadCandidates(initial)
      } catch {
        /* 拦截器已 toast */
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [workId, loadCandidates])

  const selectVersion = (id: string) => {
    setSelectedVersionId(id)
    setCandidates([])
    void loadCandidates(id)
  }

  const onAdopt = async (c: Candidate) => {
    try {
      await adoptCandidate(c.id)
      setCandidates((prev) => prev.map((x) => ({ ...x, adopted: x.id === c.id })))
      toast(`已采用候选 ${c.label} 为当前版本定稿`)
      // 采用会改变后端 current_version_id，刷新版本树「当前」标记
      try {
        if (workId) {
          const tree = await getVersionTree(workId)
          setCurrentVersionId(tree.current_version_id)
          setSelectedVersionId(tree.current_version_id)
        }
      } catch {
        /* 标记刷新失败不阻塞主流程 */
      }
    } catch {
      /* 40901 重复采用已 toast */
    }
  }

  const onPlay = (c: Candidate) => {
    const preview = c.files.find((f) => f.kind === 'preview')
    if (!preview) {
      toast('该候选暂无预览音频', 'warn')
      return
    }
    void playTrack({
      fileId: preview.file_id,
      title: `${work?.title ?? '作品'} · 候选 ${c.label}`,
      subtitle: `${work?.model ?? ''} · ${c.bpm} BPM · ${keyLabel(c.key)}`,
      durationSec: c.duration_sec,
    })
  }

  const startEdit = () => {
    if (!work) return
    setTitleDraft(work.title)
    setTagsDraft(work.tags.join(', '))
    setEditing(true)
  }

  const saveEdit = async () => {
    if (!work || !workId) return
    const title = titleDraft.trim()
    if (title.length < 1 || title.length > 50) {
      toast('标题须为 1~50 字', 'warn')
      return
    }
    const tags = tagsDraft
      .split(/[,，\n]+/)
      .map((t) => t.trim())
      .filter(Boolean)
    if (tags.length > 8) {
      toast('标签最多 8 个', 'warn')
      return
    }
    if (tags.some((t) => t.length < 1 || t.length > 12)) {
      toast('每个标签须为 1~12 字', 'warn')
      return
    }
    setSaving(true)
    try {
      const updated = await patchWork(workId, { title, tags })
      setWork((prev) => (prev ? { ...prev, title: updated.title, tags: updated.tags } : prev))
      setEditing(false)
      toast('作品信息已更新')
    } catch {
      /* 拦截器已 toast（40001 校验失败等） */
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="py-20 text-center text-[12px]" style={{ color: 'var(--dim)' }}>
        加载中…
      </div>
    )
  }
  if (!work) {
    return (
      <div className="py-20 text-center">
        <div className="text-[13px]" style={{ color: 'var(--muted)' }}>作品不存在或无权访问</div>
        <button className="btn btn-ghost text-[11px] mt-4" onClick={() => navigate('/library')}>返回作品库</button>
      </div>
    )
  }

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4 flex items-end justify-between flex-wrap gap-3">
        <div className="min-w-0">
          <div className="label">Work / 作品详情 · {work.display_code}</div>
          {editing ? (
            <div className="mt-2 flex flex-col gap-2 max-w-[560px]">
              <input
                type="text"
                value={titleDraft}
                maxLength={50}
                placeholder="标题（1~50 字）"
                onChange={(e) => setTitleDraft(e.target.value)}
                className="!text-[14px]"
                autoFocus
              />
              <input
                type="text"
                value={tagsDraft}
                placeholder="标签，逗号分隔（最多 8 个，每个 1~12 字）"
                onChange={(e) => setTagsDraft(e.target.value)}
                className="!text-[12px]"
              />
              <div className="flex gap-2">
                <button className="btn btn-acc !py-1.5 !px-3 text-[11px]" disabled={saving} onClick={() => void saveEdit()}>
                  {saving ? '保存中…' : '保存'}
                </button>
                <button className="btn btn-ghost !py-1.5 !px-3 text-[11px]" disabled={saving} onClick={() => setEditing(false)}>
                  取消
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 mt-1">
                <h1 className="text-[28px] font-extrabold tracking-tight truncate">{work.title}</h1>
                <button className="iconbtn shrink-0" title="编辑标题与标签" onClick={startEdit}>
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
                    <path d="M11.3 1.7l3 3L5.5 13.5l-3.7.7.7-3.7zM10 3l3 3" />
                  </svg>
                </button>
              </div>
              {work.tags.length > 0 && (
                <div className="flex gap-1 mt-1.5 flex-wrap">
                  {work.tags.map((t) => (
                    <span key={t} className="text-[10px] px-1.5 py-0.5" style={{ background: 'var(--bg3)', color: 'var(--muted)' }}>
                      {t}
                    </span>
                  ))}
                </div>
              )}
              <div className="flex items-center gap-3 text-[11px] mt-2" style={{ color: 'var(--muted)' }}>
                <span className="num">{keyLabel(work.key)}</span>
                <span className="num">{work.bpm} BPM</span>
                <span className="num">{formatDuration(work.duration_sec)}</span>
                <span>{work.model}</span>
                <span>版本 ×{work.version_count}</span>
              </div>
            </>
          )}
        </div>
        <button className="btn btn-ghost !py-1.5 !px-3 text-[11px]" onClick={() => navigate('/library')}>
          ← 返回作品库
        </button>
      </header>

      <div className="grid grid-cols-[220px_1fr] rule-t flex-1 min-h-0">
        {/* 版本树 */}
        <div className="border-r px-5 py-5 overflow-y-auto" style={{ borderColor: 'var(--line)' }}>
          <div className="label">版本树</div>
          <div className="vtree mt-3">
            {nodes.map((n) => (
              <div
                key={n.id}
                className={`vnode ${n.id === selectedVersionId ? 'cur' : ''}`}
                style={{ marginLeft: depthOf(nodes, n) * 14 }}
                onClick={() => selectVersion(n.id)}
                title={`${versionSourceLabel(n.source)} · 候选 ×${n.candidate_count}`}
              >
                <span className="dot"></span>
                {n.version_no} · {versionSourceLabel(n.source)}
                {n.id === currentVersionId && (
                  <span className="text-[9px] ml-1 px-1 font-bold" style={{ background: 'var(--acc-dim)', color: 'var(--acc)' }}>
                    当前
                  </span>
                )}
              </div>
            ))}
          </div>
          {selectedVersionId && (
            <div className="mt-6">
              <ExportPanel versionId={selectedVersionId} />
            </div>
          )}
        </div>

        {/* 候选列表 */}
        <div className="px-6 py-5 overflow-y-auto">
          <div className="flex items-center justify-between">
            <div className="label">候选 / Candidates</div>
            <div className="text-[11px]" style={{ color: 'var(--dim)' }}>试听低码流 · 采用后可导出</div>
          </div>
          {candidates.length === 0 ? (
            <div className="border border-dashed mt-3 py-16 text-center text-[12px]" style={{ borderColor: 'var(--line)', color: 'var(--dim)' }}>
              该版本暂无候选
            </div>
          ) : (
            <div className="mt-3 space-y-3">
              {candidates.map((c, i) => (
                <div className="card pop" key={c.id} style={{ animationDelay: `${i * 0.1}s` }}>
                  <div className="flex items-center gap-4 px-4 py-3">
                    <div className="cover flex items-center justify-center cursor-pointer" style={{ background: i ? '#1c2b1f' : '#232323', border: '1px solid var(--line)' }} onClick={() => onPlay(c)} title="试听">
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="var(--acc)">
                        <path d="M5 3l8 5-8 5z" />
                      </svg>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-semibold">候选 {c.label}</span>
                        <span className="text-[9px] px-1.5 py-0.5 font-bold num" style={{ background: 'var(--acc-dim)', color: 'var(--acc)' }}>
                          {c.quality_score == null ? '外部模型' : `AI 质量 ${c.quality_score}`}
                        </span>
                        {c.adopted && (
                          <span className="text-[9px] px-1.5 py-0.5 font-bold" style={{ background: 'var(--acc)', color: '#000' }}>已定稿</span>
                        )}
                      </div>
                      <div className="flex gap-1.5 mt-1.5 flex-wrap">
                        {c.style_tags.slice(0, 5).map((t) => (
                          <span key={t} className="text-[10px] px-1.5 py-0.5" style={{ background: 'var(--bg3)', color: 'var(--muted)' }}>{t}</span>
                        ))}
                      </div>
                    </div>
                    <span className="text-[11px] num" style={{ color: 'var(--dim)' }}>{formatDuration(c.duration_sec)}</span>
                    <button className="iconbtn" title="试听" onClick={() => onPlay(c)}>
                      <svg viewBox="0 0 16 16" fill="currentColor"><path d="M5 3l8 5-8 5z" /></svg>
                    </button>
                    {!c.adopted && (
                      <button className="btn btn-ghost !py-1 !px-2.5 text-[11px]" onClick={() => void onAdopt(c)}>采用定稿</button>
                    )}
                  </div>
                  <div className="flex gap-1 px-4 pb-3">
                    {c.structure.map((seg, j) => {
                      const span = Math.max(0, seg.end_sec - seg.start_sec)
                      const width = c.duration_sec > 0 ? Math.max(4, (span / c.duration_sec) * 100) : 10
                      return (
                        <div key={j} className="segmini" style={{ width: `${width}%` }} title={`${SECTION_LABEL[seg.section]} · ${seg.bars} 小节`}>
                          {SECTION_LABEL[seg.section]}
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
