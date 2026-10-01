import { useCallback, useEffect, useState } from 'react'
import type { CreditTransaction, PlanInfo } from '../types/api'
import { getCreditTransactions, getPlans, switchPlan } from '../api/account'
import { checkout, openPortal, redirectToUrl } from '../api/billing'
import { useSessionStore } from '../stores/session'
import { toast } from '../stores/toast'
import { creditReasonLabel, formatDateTime, formatNum, planLabel } from '../lib/format'
import ApiKeysCard from '../components/pricing/ApiKeysCard'
import Pagination from '../components/common/Pagination'
import { PageHeader } from '../components/common/PageHeader'
import { useT } from '../i18n'

const PAGE_SIZE = 10

/** 美分 → $ 展示（P0-5：价格接口下发 USD 分值，单一事实源） */
const usd = (cents: number | null | undefined): string | null =>
  cents == null ? null : `$${(cents / 100).toFixed(2)}`

/**
 * 定价与积分：四档卡片（月/年切换）+ 积分流水表。
 * v0.7.0 支付流：付费档发起 Stripe 订阅（跳 checkout url）；免费档=降级（/subscriptions/switch）；
 * team 恒「联系销售」；另有充值积分包（kind=topup）与管理订阅（Stripe 门户）入口。
 */
export default function PricingView() {
  const [plans, setPlans] = useState<PlanInfo[]>([])
  const [salesContact, setSalesContact] = useState('')
  const [topup, setTopup] = useState<{ amount_usd: number; credits: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [yearly, setYearly] = useState(true)
  const [switching, setSwitching] = useState<string | null>(null)
  const [topupBuying, setTopupBuying] = useState(false)
  const [portalOpening, setPortalOpening] = useState(false)
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
      setSalesContact(res.sales_contact ?? '')
      setTopup(res.topup ?? null)
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

  /** 付费档：发起 Stripe 订阅（Stripe 未配置时后端返 40901，拦截器已 toast） */
  const onCheckout = async (plan: PlanInfo) => {
    if (switching) return
    setSwitching(plan.code)
    try {
      const res = await checkout({
        kind: 'subscription',
        plan: plan.code as 'pro' | 'studio',
        interval: yearly ? 'yearly' : 'monthly',
      })
      if (res?.url) {
        redirectToUrl(res.url)
        return // 整页跳转中，保持按钮态
      }
    } catch {
      /* 拦截器已 toast（40901 Stripe 未配置 / 会话过期等） */
    } finally {
      setSwitching(null)
    }
  }

  /** 免费档：降级（后端 v0.7.0 起允许降回 free） */
  const onDowngrade = async (plan: PlanInfo) => {
    if (switching) return
    setSwitching(plan.code)
    try {
      const user = await switchPlan(plan.code as 'free')
      useSessionStore.setState({ user })
      await loadPlans()
      void refreshUser()
      toast(t('pricing.switched', { name: planLabel(plan.code) }))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setSwitching(null)
    }
  }

  const onSwitch = (plan: PlanInfo) => {
    if (switching) return
    if (plan.code === 'team') {
      if (salesContact) {
        window.location.assign(
          `mailto:${salesContact}?subject=${encodeURIComponent('Meloyu Team plan')}`)
      } else {
        toast(t('pricing.contactSalesToast'), 'warn')
      }
      return
    }
    if (plan.current) return
    if (plan.code === 'free') {
      void onDowngrade(plan)
    } else {
      void onCheckout(plan)
    }
  }

  /** 充值积分包：一次性购买（kind=topup） */
  const onTopup = async () => {
    if (topupBuying) return
    setTopupBuying(true)
    try {
      const res = await checkout({ kind: 'topup' })
      if (res?.url) {
        redirectToUrl(res.url)
        return
      }
    } catch {
      /* 拦截器已 toast */
    } finally {
      setTopupBuying(false)
    }
  }

  /** 管理订阅：Stripe 客户门户（无支付记录时后端返 40901，拦截器已 toast） */
  const onPortal = async () => {
    if (portalOpening) return
    setPortalOpening(true)
    try {
      const res = await openPortal()
      if (res?.url) {
        redirectToUrl(res.url)
        return
      }
    } catch {
      /* 拦截器已 toast */
    } finally {
      setPortalOpening(false)
    }
  }

  return (
    <section className="view flex flex-col h-full">
      <PageHeader
        label={t('pricing.label')}
        title={t('pricing.title')}
        actions={
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-3 text-sm text-muted">
              {t('pricing.monthly')}
              <button className={`toggle ${yearly ? 'on' : ''}`} onClick={() => setYearly((v) => !v)}></button>
              {t('pricing.yearly')}
              <span className="badge badge-solid">{t('pricing.save20')}</span>
            </div>
            <button
              className="btn btn-ghost btn-sm"
              title={t('billing.manageTitle')}
              disabled={portalOpening}
              onClick={() => void onPortal()}
            >
              {portalOpening ? t('billing.manageOpening') : t('billing.manage')}
            </button>
          </div>
        }
      />

      {loading ? (
        <div className="rule-t py-16 text-center text-sm text-dim">
          {t('pricing.loading')}
        </div>
      ) : plans.length === 0 ? (
        <div className="rule-t py-16 text-center">
          <div className="text-sm text-dim">{t('pricing.loadFailed')}</div>
          <button className="btn btn-ghost mt-4" onClick={() => void loadPlans()}>{t('common.retry')}</button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 rule-t">
          {plans.map((p) => {
            const popular = p.code === 'studio'
            const price = yearly ? p.price_yearly : p.price_monthly
            const current = p.current || user?.plan === p.code
            return (
              <div
                key={p.code}
                className={`border-r px-7 py-8 relative ${popular ? 'border-acc bg-bg-2' : 'border-line'}`}
              >
                {popular && (
                  <div className="badge badge-solid absolute top-0 left-0">
                    {t('pricing.popular')}
                  </div>
                )}
                <div className="label" style={popular ? { color: 'var(--acc)' } : undefined}>{planLabel(p.code)}</div>
                <div className="price-num mt-4">
                  {price == null ? (p.code === 'team' ? t('pricing.customPrice') : '—') : usd(price)}
                  {price != null && (
                    <span className="text-lg font-bold text-muted">{t('pricing.perMonth')}</span>
                  )}
                </div>
                <div className="text-xs mt-1 text-dim">
                  {p.code === 'free' && t('pricing.tag.free')}
                  {p.code === 'pro' && (yearly ? t('pricing.tag.proYearly') : t('pricing.tag.yearlyBetter', { price: usd(p.price_yearly) ?? '' }))}
                  {p.code === 'studio' && (yearly ? t('pricing.tag.yearlyOnly') : t('pricing.tag.yearlyBetter', { price: usd(p.price_yearly) ?? '' }))}
                  {p.code === 'team' && t('pricing.tag.team')}
                </div>
                <ul className="mt-6 space-y-2.5 text-sm text-muted">
                  {p.features.map((f) => (
                    <li key={f}>· {f}</li>
                  ))}
                  {p.monthly_credits != null && !p.features.some((f) => f.includes('积分') || f.toLowerCase().includes('credit')) && (
                    <li>
                      · {t('pricing.monthlyCredits.pre')} <span className="num">{formatNum(p.monthly_credits)}</span> {t('pricing.monthlyCredits.post')}
                    </li>
                  )}
                </ul>
                <button
                  className={`btn w-full mt-8 ${!current && p.code !== 'team' ? 'btn-acc' : ''} ${popular && !current ? 'font-bold' : ''}`}
                  disabled={current || switching === p.code}
                  onClick={() => onSwitch(p)}
                >
                  {current
                    ? t('pricing.current')
                    : switching === p.code
                      ? p.code === 'free'
                        ? t('pricing.switching')
                        : t('billing.checkout.redirecting')
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

      {/* 充值积分包（一次性购买，积分永不过期） */}
      <div className="rule-t px-8 py-5 flex items-center justify-between gap-6 flex-wrap bg-bg-2">
        <div className="min-w-0">
          <div className="label">{t('billing.topup.label')}</div>
          <div className="text-md font-bold mt-1">{t('billing.topup.title')}</div>
          <div className="text-xs mt-1 leading-relaxed max-w-[640px] text-dim">
            {t('billing.topup.desc')}
          </div>
        </div>
        <div className="flex items-center gap-6 flex-none">
          <div className="text-right">
            <span className="num font-extrabold text-2xl tracking-tight">{topup ? usd(topup.amount_usd) : '$—'}</span>
            <div className="text-xs mt-0.5 text-muted">
              <span className="num font-bold text-acc">{topup ? formatNum(topup.credits) : '—'}</span> {t('pricing.monthlyCredits.post')}
            </div>
          </div>
          <button className="btn btn-acc !py-2.5" disabled={topupBuying} onClick={() => void onTopup()}>
            {topupBuying ? t('billing.topup.buying') : t('billing.topup.cta')}
          </button>
        </div>
      </div>

      <div className="rule-t px-8 py-4 text-xs text-dim">
        {t('pricing.footnote')}
        <span className="num font-bold mx-1 text-acc">{formatNum(user?.credits.balance ?? 0)}</span>
        {t('pricing.creditsUnit')}
      </div>

      {/* 积分流水 */}
      <div className="rule-t px-8 py-4 tx-rows">
        <div className="label mb-3">{t('pricing.tx.title')}</div>
        <div className="row !cursor-default text-dim" style={{ gridTemplateColumns: '170px 90px 110px 100px 1fr' }}>
          <span className="label">{t('pricing.tx.time')}</span>
          <span className="label">{t('pricing.tx.change')}</span>
          <span className="label">{t('pricing.tx.reason')}</span>
          <span className="label">{t('pricing.tx.balance')}</span>
          <span className="label">{t('pricing.tx.task')}</span>
        </div>
        {txs.length === 0 ? (
          <div className="py-8 text-center text-xs text-dim">{t('pricing.tx.empty')}</div>
        ) : (
          txs.map((tx) => (
            <div key={tx.id} className="row !cursor-default" style={{ gridTemplateColumns: '170px 90px 110px 100px 1fr' }}>
              <span className="text-xs num text-muted">{formatDateTime(tx.created_at)}</span>
              <span className={`text-sm num font-semibold ${tx.delta >= 0 ? 'text-acc' : 'text-txt'}`}>
                {tx.delta >= 0 ? `+${tx.delta}` : tx.delta}
              </span>
              <span className="text-xs text-muted">{creditReasonLabel(tx.reason)}</span>
              <span className="text-xs num text-muted">{formatNum(tx.balance_after)}</span>
              <span className="text-2xs num truncate text-dim">{tx.ref_task_id ?? '—'}</span>
            </div>
          ))
        )}
        <Pagination page={txPage} totalPages={txTotalPages} onChange={setTxPage} />
      </div>

      {/* 开放 API（FR-19 β） */}
      <ApiKeysCard />
    </section>
  )
}
