import { useCallback, useEffect, useState } from 'react'
import type { CreditTransaction, PlanInfo } from '../types/api'
import { getCreditTransactions, getPlans, switchPlan } from '../api/account'
import { useSessionStore } from '../stores/session'
import { toast } from '../stores/toast'
import { CREDIT_REASON_LABEL, formatDateTime, formatNum } from '../lib/format'
import Pagination from '../components/common/Pagination'

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
      toast('团队版请联系销售（MVP 演示）', 'warn')
      return
    }
    if (plan.current) return
    setSwitching(plan.code)
    try {
      const user = await switchPlan(plan.code as 'free' | 'pro' | 'studio')
      useSessionStore.setState({ user })
      await loadPlans()
      void refreshUser()
      toast(`已切换至「${plan.name}」，积分已按月发放`)
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
          <div className="label">Pricing / 定价与积分</div>
          <h1 className="text-[28px] font-extrabold tracking-tight mt-1">为创作付费，不为焦虑付费</h1>
        </div>
        <div className="flex items-center gap-3 text-[12px]" style={{ color: 'var(--muted)' }}>
          按月
          <button className={`toggle ${yearly ? 'on' : ''}`} onClick={() => setYearly((v) => !v)}></button>
          按年
          <span className="text-[11px] px-1.5 py-0.5 font-bold" style={{ background: 'var(--acc)', color: '#000' }}>
            省 20%
          </span>
        </div>
      </header>

      {loading ? (
        <div className="rule-t py-16 text-center text-[12px]" style={{ color: 'var(--dim)' }}>
          加载档位…
        </div>
      ) : plans.length === 0 ? (
        <div className="rule-t py-16 text-center">
          <div className="text-[12px]" style={{ color: 'var(--dim)' }}>档位信息加载失败</div>
          <button className="btn btn-ghost text-[11px] mt-4" onClick={() => void loadPlans()}>重试</button>
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
                    最受欢迎
                  </div>
                )}
                <div className="label" style={popular ? { color: 'var(--acc)' } : undefined}>{p.name}</div>
                <div className="price-num mt-4">
                  {price == null ? (p.code === 'team' ? '定制' : '—') : `¥${price}`}
                  {price != null && (
                    <span className="text-[16px] font-bold" style={{ color: 'var(--muted)' }}> ¥/月</span>
                  )}
                </div>
                <div className="text-[11px] mt-1" style={{ color: 'var(--dim)' }}>
                  {p.code === 'free' && '先玩起来'}
                  {p.code === 'pro' && (yearly ? '按年付 · 积分可结转' : `年付 ¥${p.price_yearly ?? ''}/月 更划算`)}
                  {p.code === 'studio' && (yearly ? '按年付' : `年付 ¥${p.price_yearly ?? ''}/月 更划算`)}
                  {p.code === 'team' && '席位 · API · 批量'}
                </div>
                <ul className="mt-6 space-y-2.5 text-[12px]" style={{ color: 'var(--muted)' }}>
                  {p.features.map((f) => (
                    <li key={f}>· {f}</li>
                  ))}
                  {p.monthly_credits != null && !p.features.some((f) => f.includes('积分')) && (
                    <li>
                      · 每月 <span className="num">{formatNum(p.monthly_credits)}</span> 积分
                    </li>
                  )}
                </ul>
                <button
                  className={`btn w-full mt-8 ${!current && p.code !== 'team' ? 'btn-acc' : ''} ${popular && !current ? 'font-bold' : ''}`}
                  disabled={current || switching === p.code}
                  onClick={() => void onSwitch(p)}
                >
                  {current
                    ? '当前方案'
                    : switching === p.code
                      ? '切换中…'
                      : p.code === 'team'
                        ? '联系销售'
                        : p.code === 'free'
                          ? '降级到免费'
                          : `升级 ${p.name}`}
                </button>
              </div>
            )
          })}
        </div>
      )}

      <div className="rule-t px-8 py-4 text-[11px]" style={{ color: 'var(--dim)' }}>
        商用授权随有效订阅生效；订阅期内生成并导出的作品保留商用权利。积分按月发放、未用完可结转。当前余额
        <span className="num font-bold mx-1" style={{ color: 'var(--acc)' }}>{formatNum(user?.credits.balance ?? 0)}</span>积分。
      </div>

      {/* 积分流水 */}
      <div className="rule-t px-8 py-4">
        <div className="label mb-3">积分流水</div>
        <div className="row !cursor-default" style={{ color: 'var(--dim)', gridTemplateColumns: '170px 90px 110px 100px 1fr' }}>
          <span className="label">时间</span>
          <span className="label">变动</span>
          <span className="label">原因</span>
          <span className="label">余额</span>
          <span className="label">关联任务</span>
        </div>
        {txs.length === 0 ? (
          <div className="py-8 text-center text-[11px]" style={{ color: 'var(--dim)' }}>暂无流水记录</div>
        ) : (
          txs.map((t) => (
            <div key={t.id} className="row" style={{ cursor: 'default', gridTemplateColumns: '170px 90px 110px 100px 1fr' }}>
              <span className="text-[11px] num" style={{ color: 'var(--muted)' }}>{formatDateTime(t.created_at)}</span>
              <span className="text-[12px] num font-semibold" style={{ color: t.delta >= 0 ? 'var(--acc)' : 'var(--txt)' }}>
                {t.delta >= 0 ? `+${t.delta}` : t.delta}
              </span>
              <span className="text-[11px]" style={{ color: 'var(--muted)' }}>{CREDIT_REASON_LABEL[t.reason] ?? t.reason}</span>
              <span className="text-[11px] num" style={{ color: 'var(--muted)' }}>{formatNum(t.balance_after)}</span>
              <span className="text-[10px] num truncate" style={{ color: 'var(--dim)' }}>{t.ref_task_id ?? '—'}</span>
            </div>
          ))
        )}
        <Pagination page={txPage} totalPages={txTotalPages} onChange={setTxPage} />
      </div>
    </section>
  )
}
