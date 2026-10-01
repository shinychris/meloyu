import { useT } from '../../i18n'

interface PaginationProps {
  page: number
  totalPages: number
  onChange: (page: number) => void
}

/** 分页器：上一页/页码窗口/下一页（对齐整体直角风格） */
export default function Pagination({ page, totalPages, onChange }: PaginationProps) {
  const t = useT()
  if (totalPages <= 1) return null
  const windowSize = 5
  let start = Math.max(1, page - Math.floor(windowSize / 2))
  const end = Math.min(totalPages, start + windowSize - 1)
  start = Math.max(1, end - windowSize + 1)
  const pages: number[] = []
  for (let i = start; i <= end; i++) pages.push(i)

  return (
    <div className="pager">
      <span className="text-2xs num mr-2 text-dim">
        {t('layout.pagination.status', { page, total: totalPages })}
      </span>
      <button className="pnum-btn" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        {t('layout.pagination.prev')}
      </button>
      {pages.map((p) => (
        <button key={p} className={`pnum-btn ${p === page ? 'on' : ''}`} onClick={() => onChange(p)}>
          {p}
        </button>
      ))}
      <button className="pnum-btn" disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
        {t('layout.pagination.next')}
      </button>
    </div>
  )
}
