import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Work } from '../types/api'
import { deleteWork, listWorks, patchWork, restoreWork } from '../api/works'
import { listTasks } from '../api/generation'
import { usePlayerStore } from '../stores/player'
import { useSessionStore } from '../stores/session'
import { useConfirmStore } from '../stores/confirm'
import { toast } from '../stores/toast'
import { useT } from '../i18n'
import { formatDuration, keyLabel } from '../lib/format'
import Pagination from '../components/common/Pagination'
import SearchInput from '../components/common/SearchInput'
import { PageHeader } from '../components/common/PageHeader'
import { EmptyState } from '../components/common/EmptyState'

type Filter = 'all' | 'draft' | 'fav' | 'trash'

const PAGE_SIZE = 20

/** 作品库：表格 + 筛选 chips + 搜索/排序 + 标签 + 收藏星标 + 回收站闭环 + 行内试听 */
export default function LibraryView() {
  const t = useT()
  const navigate = useNavigate()
  const [filter, setFilter] = useState<Filter>('all')
  const [items, setItems] = useState<Work[]>([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  /** 搜索词（q，≤50 字）：SearchInput 内部 400ms 防抖后回调写入，仅作 API 查询参数 */
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<'updated_at' | 'created_at' | 'title'>('updated_at')
  const [order, setOrder] = useState<'desc' | 'asc'>('desc')
  /**
   * 导出徽标回退表（workId → 已成功导出格式）：仅当 works 响应缺失 exported_formats
   * 字段（后端未重启/旧数据）时，由一次批量导出任务请求分组填充，替代旧的逐作品 N+1。
   */
  const [exportFallback, setExportFallback] = useState<Record<string, string[]>>({})
  const playTrack = usePlayerStore((s) => s.playTrack)
  const user = useSessionStore((s) => s.user)
  const confirm = useConfirmStore((s) => s.confirm)

  const commercial = user && user.plan !== 'free'

  /**
   * 搜索回调（SearchInput 内部 400ms 防抖后回调写入）：保持引用稳定，
   * 防抖期间视图重渲染不再触碰输入框；查询变更同时回到第 1 页。
   */
  const changeQuery = useCallback((v: string): void => {
    setQ(v)
    setPage(1)
  }, [])

  /** F-FE-02：请求序号守卫——筛选/翻页快速变更时旧响应不再覆盖新查询的结果 */
  const loadSeqRef = useRef(0)

  const load = useCallback(async () => {
    const seq = ++loadSeqRef.current
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
      if (seq !== loadSeqRef.current) return
      setItems(res.items)
      setTotalPages(res.total_pages || 1)
      setTotal(res.total)
      // 导出徽标（P2-5 修复）：优先读 works.exported_formats；字段缺失时一次批量拉取
      // 导出任务按 work_id 分组（1 次请求），不再逐作品 listTasks 造成 1+N。
      if (res.items.some((w) => !Array.isArray(w.exported_formats))) {
        try {
          const tasks = await listTasks({ type: 'export', page_size: 100 })
          if (seq !== loadSeqRef.current) return
          const next: Record<string, string[]> = {}
          for (const tk of tasks.items) {
            if (tk.status === 'succeeded' && tk.format && tk.work_id) {
              ;(next[tk.work_id] ??= []).push(tk.format)
            }
          }
          setExportFallback(next)
        } catch {
          if (seq === loadSeqRef.current) setExportFallback({}) // 徽标降级为「未导出」，不阻塞列表
        }
      } else if (seq === loadSeqRef.current) {
        setExportFallback({})
      }
    } catch {
      /* 拦截器已 toast */
    } finally {
      if (seq === loadSeqRef.current) setLoading(false)
    }
  }, [filter, page, q, sort, order])

  useEffect(() => {
    void load()
  }, [load])

  const changeFilter = (f: Filter): void => {
    setFilter(f)
    setPage(1)
  }
  const changeSort = (v: 'updated_at' | 'created_at' | 'title'): void => {
    setSort(v)
    setPage(1)
  }
  const changeOrder = (v: 'desc' | 'asc'): void => {
    setOrder(v)
    setPage(1)
  }

  /** 某作品的已导出格式：新字段优先，缺失时回退批量推导 */
  const exportsOf = useCallback(
    (w: Work): string[] => w.exported_formats ?? exportFallback[w.id] ?? [],
    [exportFallback],
  )

  const shown = filter === 'draft' ? items.filter((w) => exportsOf(w).length === 0) : items

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
      toast(t('library.toast.restored', { title: w.title }))
      void load()
    } catch {
      /* 40901 等已 toast */
    }
  }

  const onPermanentDelete = async (e: React.MouseEvent, w: Work) => {
    e.stopPropagation()
    const ok = await confirm({
      title: t('library.confirm.deleteTitle', { title: w.title }),
      description: t('library.confirm.deleteDesc'),
      confirmText: t('library.action.permanentDelete'),
      danger: true,
    })
    if (!ok) return
    try {
      await deleteWork(w.id, true)
      toast(t('library.toast.deleted'))
      void load()
    } catch {
      /* 拦截器已 toast */
    }
  }

  const onTrash = async (e: React.MouseEvent, w: Work) => {
    e.stopPropagation()
    const ok = await confirm({
      title: t('library.confirm.trashTitle', { title: w.title }),
      description: t('library.confirm.trashDesc'),
      confirmText: t('library.action.trash'),
      danger: true,
    })
    if (!ok) return
    try {
      await deleteWork(w.id, false)
      toast(t('library.toast.trashed', { title: w.title }))
      void load()
    } catch {
      /* 拦截器已 toast */
    }
  }

  const onPlay = (e: React.MouseEvent, w: Work) => {
    e.stopPropagation()
    if (!w.preview_file_id) {
      toast(t('library.toast.noPreview'), 'warn')
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
    all: t('library.filter.all', { n: filter === 'all' ? total : '' }).trim(),
    draft: t('library.filter.draft'),
    fav: t('library.filter.fav'),
    trash: t('library.filter.trash'),
  }

  return (
    <section className="view flex flex-col h-full">
      <PageHeader
        label={t('library.header.label')}
        title={filter === 'trash' ? t('library.title.trash') : t('library.title.all')}
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <SearchInput onQueryChange={changeQuery} placeholder={t('library.search.placeholder')} />
            <select
              value={sort}
              onChange={(e) => changeSort(e.target.value as 'updated_at' | 'created_at' | 'title')}
              className="text-sm"
              title={t('library.sort.title')}
            >
              <option value="updated_at">{t('library.sort.updated')}</option>
              <option value="created_at">{t('library.sort.created')}</option>
              <option value="title">{t('library.col.title')}</option>
            </select>
            <select
              value={order}
              onChange={(e) => changeOrder(e.target.value as 'desc' | 'asc')}
              className="text-sm"
              title={t('library.order.title')}
            >
              <option value="desc">{t('library.order.desc')}</option>
              <option value="asc">{t('library.order.asc')}</option>
            </select>
            {(['all', 'draft', 'fav', 'trash'] as Filter[]).map((f) => (
              <button type="button" key={f} className={`chip ${filter === f ? 'on' : ''}`} onClick={() => changeFilter(f)}>
                {chipLabel[f]}
              </button>
            ))}
          </div>
        }
      />
      <div className="rule-t flex-1 overflow-y-auto list-scroll">
        {filter !== 'trash' && (
          <div className="row row-works !cursor-default text-dim">
            <span className="label">{t('library.col.no')}</span>
            <span className="label">{t('library.col.cover')}</span>
            <span className="label">{t('library.col.title')}</span>
            <span className="label">{t('library.col.key')}</span>
            <span className="label">{t('library.col.bpm')}</span>
            <span className="label">{t('library.col.export')}</span>
            <span className="label">{t('library.col.license')}</span>
            <span></span>
          </div>
        )}
        {loading && items.length === 0 ? (
          <div className="py-16 text-center text-sm text-dim">{t('common.loading')}</div>
        ) : shown.length === 0 ? (
          <EmptyState
            title={filter === 'trash' ? t('library.empty.trashTitle') : t('library.empty.title')}
            hint={filter === 'trash' ? t('library.empty.trashHint') : t('library.empty.hint')}
            actionLabel={filter !== 'trash' ? t('library.empty.cta') : undefined}
            onAction={() => navigate('/studio')}
          />
        ) : filter === 'trash' ? (
          shown.map((w) => (
            <div className="row row-works" key={w.id}>
              <span className="text-xs num text-dim">{w.display_code}</span>
              <div className="cover border border-line" style={{ background: w.cover_color ?? 'var(--bg3)' }}></div>
              <span className="text-base font-semibold truncate">{w.title}</span>
              <span className="text-sm text-muted">{keyLabel(w.key)}</span>
              <span className="text-sm num text-muted">{w.bpm}</span>
              <span className="text-xs text-muted">{formatDuration(w.duration_sec)}</span>
              <span className="text-xs text-dim">{w.trashed_at ? t('library.trashBadge') : ''}</span>
              <div className="flex gap-1.5 justify-end">
                <button className="btn btn-ghost btn-sm" onClick={(e) => void onRestore(e, w)}>
                  {t('library.action.restore')}
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ borderColor: 'var(--bad)', color: 'var(--bad)' }}
                  onClick={(e) => void onPermanentDelete(e, w)}
                >
                  {t('library.action.permanentDelete')}
                </button>
              </div>
            </div>
          ))
        ) : (
          shown.map((w) => {
            const exports = exportsOf(w)
            const badge =
              exports.length > 0 ? [...new Set(exports)].map((f) => f.toUpperCase()).join(' · ') : t('library.export.none')
            return (
              <div className="row row-works" key={w.id} onClick={() => navigate(`/works/${w.id}`)}>
                <span className="text-xs num text-dim">{w.display_code}</span>
                <div className="cover border border-line" style={{ background: w.cover_color ?? 'var(--bg3)' }}></div>
                <div className="min-w-0">
                  <div className="text-base font-semibold truncate">{w.title}</div>
                  {w.tags.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {w.tags.slice(0, 4).map((tg) => (
                        <span key={tg} className="badge">
                          {tg}
                        </span>
                      ))}
                      {w.tags.length > 4 && <span className="text-2xs text-dim">+{w.tags.length - 4}</span>}
                    </div>
                  )}
                </div>
                <span className="text-sm text-muted">{keyLabel(w.key)}</span>
                <span className="text-sm num text-muted">{w.bpm}</span>
                <span className="text-xs text-muted">{badge}</span>
                <span className={`text-xs ${commercial ? 'text-acc' : 'text-muted'}`}>
                  {commercial ? t('library.license.commercial') : t('library.license.nonCommercial')}
                </span>
                <div className="flex gap-2 justify-end items-center">
                  <button
                    className={`star-btn ${w.favorite ? 'on' : ''}`}
                    title={w.favorite ? t('library.fav.remove') : t('library.fav.add')}
                    onClick={(e) => void toggleFav(e, w)}
                  >
                    <svg viewBox="0 0 16 16" fill={w.favorite ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.4">
                      <path d="M8 1.6l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.4l-3.8 2 .7-4.3-3.1-3 4.3-.6z" />
                    </svg>
                  </button>
                  <button className="iconbtn" title={t('library.action.preview')} onClick={(e) => onPlay(e, w)}>
                    <svg viewBox="0 0 16 16" fill="currentColor">
                      <path d="M5 3l8 5-8 5z" />
                    </svg>
                  </button>
                  <button
                    className="iconbtn"
                    title={t('library.action.trash')}
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
