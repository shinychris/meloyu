import { useCallback, useEffect, useState } from 'react'
import type { CreditTransaction } from '../../types/api'
import { getCreditTransactions } from '../../api/account'
import { creditReasonLabel, formatDateTime, formatNum } from '../../lib/format'
import Pagination from '../common/Pagination'
import { useT } from '../../i18n'

const PAGE_SIZE = 10

/**
 * 用量/积分记录表（SettingsView 与 PricingView 共用）。
 * showBalance=false（license 纯计量模式）隐藏余额列——桌面买断形态没有
 * 「余额」语义，流水只作用量统计参考。
 */
export default function UsageRecords({ showBalance = true }: { showBalance?: boolean }) {
  const t = useT()
  const [txs, setTxs] = useState<CreditTransaction[]>([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)

  const load = useCallback(async (p: number) => {
    try {
      const res = await getCreditTransactions({ page: p, page_size: PAGE_SIZE })
      setTxs(res.items)
      setTotalPages(res.total_pages || 1)
    } catch {
      /* 拦截器已 toast */
    }
  }, [])

  useEffect(() => {
    void load(page)
  }, [load, page])

  const cols = showBalance
    ? '170px 90px 110px 100px 1fr'
    : '170px 90px 110px 1fr'

  return (
    <div>
      <div className="row !cursor-default text-dim" style={{ gridTemplateColumns: cols }}>
        <span className="label">{t('pricing.tx.time')}</span>
        <span className="label">{t('pricing.tx.change')}</span>
        <span className="label">{t('pricing.tx.reason')}</span>
        {showBalance && <span className="label">{t('pricing.tx.balance')}</span>}
        <span className="label">{t('pricing.tx.task')}</span>
      </div>
      {txs.length === 0 ? (
        <div className="py-8 text-center text-xs text-dim">{t('pricing.tx.empty')}</div>
      ) : (
        txs.map((tx) => (
          <div key={tx.id} className="row !cursor-default" style={{ gridTemplateColumns: cols }}>
            <span className="text-xs num text-muted">{formatDateTime(tx.created_at)}</span>
            <span className={`text-sm num font-semibold ${tx.delta >= 0 ? 'text-acc' : 'text-txt'}`}>
              {tx.delta >= 0 ? `+${tx.delta}` : tx.delta}
            </span>
            <span className="text-xs text-muted">{creditReasonLabel(tx.reason)}</span>
            {showBalance && (
              <span className="text-xs num text-muted">{formatNum(tx.balance_after)}</span>
            )}
            <span className="text-2xs num truncate text-dim">{tx.ref_task_id ?? '—'}</span>
          </div>
        ))
      )}
      <Pagination page={page} totalPages={totalPages} onChange={setPage} />
    </div>
  )
}
