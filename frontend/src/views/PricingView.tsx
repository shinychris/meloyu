import { useCallback, useEffect, useState } from 'react'
import type { CreditTransaction, PlanInfo } from '../types/api'
import { getCreditTransactions, getPlans, switchPlan } from '../api/account'
import { useSessionStore } from '../stores/session'
import { toast } from '../stores/toast'
import { creditReasonLabel, formatDateTime, formatNum, planLabel } from '../lib/format'
import Pagination from '../components/common/Pagination'
import { useT } from '../i18n'

const PAGE_SIZE = 10

/** 定价与积分：四档卡片（月/年切换）+ 升级调订阅接口 + 积分流水表 */
export default function PricingView() {
  const [plans, setPlans] = useState<PlanInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [yearly, setYearly] = useState(true)
  const [switching, setSwitching] = useState<string | null>(null)
  const [txs, setTxs] = useState<CreditTransaction[]>([])
  const [txPage, setTxPage] = useState(1)
  const [txTotalPages, setTxTotalPages] = useState(1)
  const { user, refreshUser } = useSessionStore()
  const t = useT()

  const loadPlans = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getPlans()
      setPlans(res.plans)
    } catch {
      /* 拦截器已 toast */
    } finally {
      setLoading(false)
    }
  }, [])

  const loadTxs = useCallback(async (page: number) => {
    try {
      const res = await getCreditTransactions({ page, page_size: PAGE_SIZE })
      setTxs(res.items)
      setTxTotalPages(res.total_pages || 1)
    } catch {
      /* 拦截器已 toast */
    }
  }, [])

  useEffect(() => {
    void loadPlans()
  }, [loadPlans])

  useEffect(() => {
    void loadTxs(txPage)
  }, [loadTxs, txPage])

  const onSwitch = async (plan: PlanInfo) => {
    if (switching) return
    if (plan.code === 'team') {
      toast(t('pricing.contactSalesToast'), 'warn')
      return
    }
    if (plan.current) return
    setSwitching(plan.code)
    try {
      const user = await switchPlan(plan.code as 'free' | 'pro' | 'studio')
      useSessionStore.setState({ user })
      await loadPlans()
      void refreshUser()
      toast(t('pricing.switched', { name: planLabel(plan.code) }))
    } catch {
      /* 拦截器已 toast（40001 团队版等） */
    } finally {
      setSwitching(null)
    }
  }

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4 flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="label">{t('pricing.label')}</div>
          <h1 className="text-[28px] font-extrabold tracking-tight mt-1">{t('pricing.title')}</h1>
        </div>
        <div className="flex items-center gap-3 text-[12px]" style={{ color: 'var(--muted)' }}>
          {t('pricing.monthly')}
          <button className={`toggle ${yearly ? 'on' : ''}`} onClick={() => setYearly((v) => !v)}></button>
          {t('pricing.yearly')}
          <span className="text-[11px] px-1.5 py-0.5 font-bold" style={{ background: 'var(--acc)', color: '#000' }}>
            {t('pricing.save20')}
          </span>
        </div>
      </header>

      {loading ? (
        <div className="rule-t py-16 text-center text-[12px]" style={{ color: 'var(--dim)' }}>
          {t('pricing.loading')}
        </div>
      ) : plans.length === 0 ? (
        <div className="rule-t py-16 text-center">
          <div className="text-[12px]" style={{ color: 'var(--dim)' }}>{t('pricing.loadFailed')}</div>
          <button className="btn btn-ghost text-[11px] mt-4" onClick={() => void loadPlans()}>{t('common.retry')}</button>
        </div>
      ) : (
        <div className="grid grid-cols-4 rule-t">
          {plans.map((p) => {
            const popular = p.code === 'studio'
            const price = yearly ? p.price_yearly : p.price_monthly
            const current = p.current || user?.plan === p.code
            return (
              <div
                key={p.code}
                className={`border-r px-7 py-8 relative ${popular ? '' : ''}`}
                style={
                  popular
                    ? { borderColor: 'var(--acc)', background: 'var(--bg2)' }
                    : { borderColor: 'var(--line)' }
                }
              >
                {popular && (
                  <div className="absolute top-0 left-0 text-[10px] font-bold px-2 py-1" style={{ background: 'var(--acc)', color: '#000' }}>
                    {t('pricing.popular')}
                  </div>
                )}
                <div className="label" style={popular ? { color: 'var(--acc)' } : undefined}>{planLabel(p.code)}</div>
                <div className="price-num mt-4">
                  {price == null ? (p.code === 'team' ? t('pricing.customPrice') : '—') : `¥${price}`}
                  {price != null && (
                    <span className="text-[16px] font-bold" style={{ color: 'var(--muted)' }}>{t('pricing.perMonth')}</span>
                  )}
                </div>
                <div className="text-[11px] mt-1" style={{ color: 'var(--dim)' }}>
                  {p.code === 'free' && t('pricing.tag.free')}
                  {p.code === 'pro' && (yearly ? t('pricing.tag.proYearly') : t('pricing.tag.yearlyBetter', { price: p.price_yearly ?? '' }))}
                  {p.code === 'studio' && (yearly ? t('pricing.tag.yearlyOnly') : t('pricing.tag.yearlyBetter', { price: p.price_yearly ?? '' }))}
                  {p.code === 'team' && t('pricing.tag.team')}
                </div>
                <ul className="mt-6 space-y-2.5 text-[12px]" style={{ color: 'var(--muted)' }}>
                  {p.features.map((f) => (
                    <li key={f}>· {f}</li>
                  ))}
                  {p.monthly_credits != null && !p.features.some((f) => f.includes('积分') || /credit/i.test(f)) && (
                    <li>
                      · {t('pricing.monthlyCredits.pre')} <span className="num">{formatNum(p.monthly_credits)}</span> {t('pricing.monthlyCredits.post')}
                    </li>
                  )}
                </ul>
                <button
                  className={`btn w-full mt-8 ${!current && p.code !== 'team' ? 'btn-acc' : ''} ${popular && !current ? 'font-bold' : ''}`}
                  disabled={current || switching === p.code}
                  onClick={() => void onSwitch(p)}
                >
                  {current
                    ? t('pricing.current')
                    : switching === p.code
                      ? t('pricing.switching')
                      : p.code === 'team'
                        ? t('pricing.contactSales')
                        : p.code === 'free'
                          ? t('pricing.downgrade')
                          : t('pricing.upgrade', { name: planLabel(p.code) })}
                </button>
              </div>
            )
          })}
        </div>
      )}

      <div className="rule-t px-8 py-4 text-[11px]" style={{ color: 'var(--dim)' }}>
        {t('pricing.footnote')}
        <span className="num font-bold mx-1" style={{ color: 'var(--acc)' }}>{formatNum(user?.credits.balance ?? 0)}</span>
        {t('pricing.creditsUnit')}
      </div>

      {/* 积分流水 */}
      <div className="rule-t px-8 py-4">
        <div className="label mb-3">{t('pricing.tx.title')}</div>
        <div className="row !cursor-default" style={{ color: 'var(--dim)', gridTemplateColumns: '170px 90px 110px 100px 1fr' }}>
          <span className="label">{t('pricing.tx.time')}</span>
          <span className="label">{t('pricing.tx.change')}</span>
          <span className="label">{t('pricing.tx.reason')}</span>
          <span className="label">{t('pricing.tx.balance')}</span>
          <span className="label">{t('pricing.tx.task')}</span>
        </div>
        {txs.length === 0 ? (
          <div className="py-8 text-center text-[11px]" style={{ color: 'var(--dim)' }}>{t('pricing.tx.empty')}</div>
        ) : (
          txs.map((tx) => (
            <div key={tx.id} className="row" style={{ cursor: 'default', gridTemplateColumns: '170px 90px 110px 100px 1fr' }}>
              <span className="text-[11px] num" style={{ color: 'var(--muted)' }}>{formatDateTime(tx.created_at)}</span>
              <span className="text-[12px] num font-semibold" style={{ color: tx.delta >= 0 ? 'var(--acc)' : 'var(--txt)' }}>
                {tx.delta >= 0 ? `+${tx.delta}` : tx.delta}
              </span>
              <span className="text-[11px]" style={{ color: 'var(--muted)' }}>{creditReasonLabel(tx.reason)}</span>
              <span className="text-[11px] num" style={{ color: 'var(--muted)' }}>{formatNum(tx.balance_after)}</span>
              <span className="text-[10px] num truncate" style={{ color: 'var(--dim)' }}>{tx.ref_task_id ?? '—'}</span>
            </div>
          ))
        )}
        <Pagination page={txPage} totalPages={txTotalPages} onChange={setTxPage} />
      </div>
    </section>
  )
}
