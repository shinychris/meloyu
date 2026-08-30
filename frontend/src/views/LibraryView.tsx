import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Work } from '../types/api'
import { deleteWork, listWorks, patchWork, restoreWork } from '../api/works'
import { listTasks } from '../api/generation'
import { usePlayerStore } from '../stores/player'
import { useSessionStore } from '../stores/session'
import { useConfirmStore } from '../stores/confirm'
import { toast } from '../stores/toast'
import { formatDuration, keyLabel } from '../lib/format'
import Pagination from '../components/common/Pagination'

type Filter = 'all' | 'draft' | 'fav' | 'trash'

const PAGE_SIZE = 20

/** 作品库：表格 + 筛选 chips + 搜索/排序 + 标签 + 收藏星标 + 回收站闭环 + 行内试听 */
export default function LibraryView() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<Filter>('all')
  const [items, setItems] = useState<Work[]>([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  /** 搜索（q，≤50 字，400ms 防抖）与排序（sort/order，契约 §1.3/§7.1） */
  const [qInput, setQInput] = useState('')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<'updated_at' | 'created_at' | 'title'>('updated_at')
  const [order, setOrder] = useState<'desc' | 'asc'>('desc')
  /** workId → 已成功导出的格式列表（导出徽标由导出任务推导，契约 §14 R1） */
  const [exportMap, setExportMap] = useState<Record<string, string[]>>({})
  const playTrack = usePlayerStore((s) => s.playTrack)
  const user = useSessionStore((s) => s.user)
  const confirm = useConfirmStore((s) => s.confirm)

  const commercial = user && user.plan !== 'free'

  useEffect(() => {
    const t = setTimeout(() => setQ(qInput.trim().slice(0, 50)), 400)
    return () => clearTimeout(t)
  }, [qInput])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listWorks({
        status: filter === 'trash' ? 'trash' : 'active',
        favorite: filter === 'fav' ? true : undefined,
        q: q || undefined,
        sort,
        order,
        page,
        page_size: PAGE_SIZE,
      })
      setItems(res.items)
      setTotalPages(res.total_pages || 1)
      setTotal(res.total)
      // 导出徽标：按 work 拉取成功导出任务（种子数据量小，逐个查询可接受）
      const next: Record<string, string[]> = {}
      await Promise.all(
        res.items.map(async (w) => {
          try {
            const tasks = await listTasks({ type: 'export', work_id: w.id, page_size: 100 })
            next[w.id] = tasks.items
              .filter((t) => t.status === 'succeeded' && t.format)
              .map((t) => t.format as string)
          } catch {
            next[w.id] = []
          }
        }),
      )
      setExportMap((prev) => ({ ...prev, ...next }))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setLoading(false)
    }
  }, [filter, page, q, sort, order])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setPage(1)
  }, [filter, q, sort, order])

  const shown = filter === 'draft' ? items.filter((w) => (exportMap[w.id] ?? []).length === 0) : items

  const toggleFav = async (e: React.MouseEvent, w: Work) => {
    e.stopPropagation()
    setItems((prev) => prev.map((x) => (x.id === w.id ? { ...x, favorite: !x.favorite } : x)))
    try {
      await patchWork(w.id, { favorite: !w.favorite })
    } catch {
      setItems((prev) => prev.map((x) => (x.id === w.id ? { ...x, favorite: w.favorite } : x)))
    }
  }

  const onRestore = async (e: React.MouseEvent, w: Work) => {
    e.stopPropagation()
    try {
      await restoreWork(w.id)
      toast(`已恢复「${w.title}」`)
      void load()
    } catch {
      /* 40901 等已 toast */
    }
  }

  const onPermanentDelete = async (e: React.MouseEvent, w: Work) => {
    e.stopPropagation()
    const ok = await confirm({
      title: `永久删除「${w.title}」？`,
      description: '将级联删除全部版本、候选与音频文件，不可恢复。此操作不可撤销。',
      confirmText: '永久删除',
      danger: true,
    })
    if (!ok) return
    try {
      await deleteWork(w.id, true)
      toast('已永久删除')
      void load()
    } catch {
      /* 拦截器已 toast */
    }
  }

  const onTrash = async (e: React.MouseEvent, w: Work) => {
    e.stopPropagation()
    const ok = await confirm({
      title: `移入回收站「${w.title}」？`,
      description: '作品将进入回收站并保留 30 天，期间可随时恢复；已生成的版本与音频不受影响。',
      confirmText: '移入回收站',
      danger: true,
    })
    if (!ok) return
    try {
      await deleteWork(w.id, false)
      toast(`已将「${w.title}」移入回收站`)
      void load()
    } catch {
      /* 拦截器已 toast */
    }
  }

  const onPlay = (e: React.MouseEvent, w: Work) => {
    e.stopPropagation()
    if (!w.preview_file_id) {
      toast('该作品暂无预览音频（尚未采用候选）', 'warn')
      return
    }
    void playTrack({
      fileId: w.preview_file_id,
      title: w.title,
      subtitle: `${w.bpm} BPM · ${keyLabel(w.key)}`,
      durationSec: w.duration_sec,
    })
  }

  const chipLabel: Record<Filter, string> = {
    all: `全部 ${filter === 'all' ? total : ''}`.trim(),
    draft: '草稿',
    fav: '已收藏',
    trash: '回收站',
  }

  return (
    <section className="view flex flex-col h-full">
      <header className="flex items-end justify-between px-8 pt-6 pb-4 flex-wrap gap-3">
        <div>
          <div className="label">Library / 作品库</div>
          <h1 className="text-[28px] font-extrabold tracking-tight mt-1">
            {filter === 'trash' ? '回收站' : '全部作品'}
          </h1>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="text"
            value={qInput}
            maxLength={50}
            placeholder="搜索标题 / 歌词…"
            onChange={(e) => setQInput(e.target.value)}
            className="!w-[220px] !text-[12px]"
            style={{ padding: '6px 10px' }}
          />
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as 'updated_at' | 'created_at' | 'title')}
            className="!text-[12px]"
            title="排序字段"
          >
            <option value="updated_at">最近更新</option>
            <option value="created_at">创建时间</option>
            <option value="title">标题</option>
          </select>
          <select
            value={order}
            onChange={(e) => setOrder(e.target.value as 'desc' | 'asc')}
            className="!text-[12px]"
            title="排序方向"
          >
            <option value="desc">降序</option>
            <option value="asc">升序</option>
          </select>
          {(['all', 'draft', 'fav', 'trash'] as Filter[]).map((f) => (
            <span key={f} className={`chip ${filter === f ? 'on' : ''}`} onClick={() => setFilter(f)}>
              {chipLabel[f]}
            </span>
          ))}
        </div>
      </header>
      <div className="rule-t flex-1 overflow-y-auto">
        {filter !== 'trash' && (
          <div className="row !cursor-default" style={{ color: 'var(--dim)' }}>
            <span className="label">编号</span>
            <span className="label">封面</span>
            <span className="label">标题</span>
            <span className="label">调性</span>
            <span className="label">BPM</span>
            <span className="label">导出</span>
            <span className="label">授权</span>
            <span></span>
          </div>
        )}
        {loading && items.length === 0 ? (
          <div className="py-16 text-center text-[12px]" style={{ color: 'var(--dim)' }}>
            加载中…
          </div>
        ) : shown.length === 0 ? (
          <div className="py-16 text-center">
            <div className="text-[13px] font-semibold" style={{ color: 'var(--muted)' }}>
              {filter === 'trash' ? '回收站是空的' : '还没有作品'}
            </div>
            <div className="text-[11px] mt-2" style={{ color: 'var(--dim)' }}>
              {filter === 'trash' ? '删除的作品会在这里保留 30 天' : '去创作工作台生成你的第一首歌'}
            </div>
            {filter !== 'trash' && (
              <button className="btn btn-ghost text-[11px] mt-4" onClick={() => navigate('/studio')}>
                进入工作台 →
              </button>
            )}
          </div>
        ) : filter === 'trash' ? (
          shown.map((w) => (
            <div className="row" key={w.id}>
              <span className="text-[11px] num" style={{ color: 'var(--dim)' }}>{w.display_code}</span>
              <div className="cover" style={{ background: w.cover_color ?? '#232323', border: '1px solid var(--line)' }}></div>
              <span className="text-[13px] font-semibold truncate">{w.title}</span>
              <span className="text-[12px]" style={{ color: 'var(--muted)' }}>{keyLabel(w.key)}</span>
              <span className="text-[12px] num" style={{ color: 'var(--muted)' }}>{w.bpm}</span>
              <span className="text-[11px]" style={{ color: 'var(--muted)' }}>{formatDuration(w.duration_sec)}</span>
              <span className="text-[11px]" style={{ color: 'var(--dim)' }}>
                {w.trashed_at ? '回收站' : ''}
              </span>
              <div className="flex gap-1.5 justify-end">
                <button className="btn btn-ghost !py-1 !px-2.5 text-[11px]" onClick={(e) => void onRestore(e, w)}>
                  恢复
                </button>
                <button
                  className="btn btn-ghost !py-1 !px-2.5 text-[11px]"
                  style={{ borderColor: 'var(--bad)', color: 'var(--bad)' }}
                  onClick={(e) => void onPermanentDelete(e, w)}
                >
                  永久删除
                </button>
              </div>
            </div>
          ))
        ) : (
          shown.map((w) => {
            const exports = exportMap[w.id] ?? []
            const badge = exports.length > 0 ? [...new Set(exports)].map((f) => f.toUpperCase()).join(' · ') : '未导出'
            return (
              <div className="row" key={w.id} onClick={() => navigate(`/works/${w.id}`)}>
                <span className="text-[11px] num" style={{ color: 'var(--dim)' }}>{w.display_code}</span>
                <div className="cover" style={{ background: w.cover_color ?? '#232323', border: '1px solid var(--line)' }}></div>
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold truncate">{w.title}</div>
                  {w.tags.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {w.tags.slice(0, 4).map((t) => (
                        <span key={t} className="text-[10px] px-1.5 py-0.5" style={{ background: 'var(--bg3)', color: 'var(--muted)' }}>
                          {t}
                        </span>
                      ))}
                      {w.tags.length > 4 && (
                        <span className="text-[10px]" style={{ color: 'var(--dim)' }}>+{w.tags.length - 4}</span>
                      )}
                    </div>
                  )}
                </div>
                <span className="text-[12px]" style={{ color: 'var(--muted)' }}>{keyLabel(w.key)}</span>
                <span className="text-[12px] num" style={{ color: 'var(--muted)' }}>{w.bpm}</span>
                <span className="text-[11px]" style={{ color: 'var(--muted)' }}>{badge}</span>
                <span className="text-[11px]" style={{ color: commercial ? 'var(--acc)' : 'var(--muted)' }}>
                  {commercial ? '商用授权' : '非商用'}
                </span>
                <div className="flex gap-2 justify-end items-center">
                  <button
                    className={`star-btn ${w.favorite ? 'on' : ''}`}
                    title={w.favorite ? '取消收藏' : '收藏'}
                    onClick={(e) => void toggleFav(e, w)}
                  >
                    <svg viewBox="0 0 16 16" fill={w.favorite ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.4">
                      <path d="M8 1.6l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.4l-3.8 2 .7-4.3-3.1-3 4.3-.6z" />
                    </svg>
                  </button>
                  <button className="iconbtn" title="试听" onClick={(e) => onPlay(e, w)}>
                    <svg viewBox="0 0 16 16" fill="currentColor">
                      <path d="M5 3l8 5-8 5z" />
                    </svg>
                  </button>
                  <button
                    className="iconbtn"
                    title="移入回收站"
                    onClick={(e) => void onTrash(e, w)}
                  >
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
                      <path d="M2.5 4.5h11M6 4.5V3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1.5M4 4.5l.6 8a1 1 0 0 0 1 .9h4.8a1 1 0 0 0 1-.9l.6-8M6.5 7v4M9.5 7v4" />
                    </svg>
                  </button>
                </div>
              </div>
            )
          })
        )}
        <Pagination page={page} totalPages={totalPages} onChange={setPage} />
      </div>
    </section>
  )
}
