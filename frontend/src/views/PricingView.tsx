import { useCallback, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import type { PlanInfo } from '../types/api'
import { getPlans } from '../api/account'
import { useSessionStore } from '../stores/session'
import { formatNum, planLabel } from '../lib/format'
import ApiKeysCard from '../components/pricing/ApiKeysCard'
import UsageRecords from '../components/settings/UsageRecords'
import { PageHeader } from '../components/common/PageHeader'
import { useT } from '../i18n'

/** 美分 → $ 展示 */
const usd2 = (cents: number | null | undefined): string | null =>
  cents == null ? null : `$${(cents / 100).toFixed(2)}`

/**
 * 定价与积分（cloud 存量专用）：订阅停售公告 + 档位配额参考（只读）+
 * 积分流水 + 开放 API。
 *
 * v0.17.0：license（桌面买断）形态的授权激活与用量统计已迁入系统设置页
 * （/settings），本页在该形态下直接重定向过去。
 */
export default function PricingView() {
  const [plans, setPlans] = useState<PlanInfo[]>([])
  const { user, license } = useSessionStore()
  const t = useT()

  const isLicense = license?.billing_mode === 'license'

  const loadPlans = useCallback(async () => {
    try {
      const res = await getPlans()
      setPlans(res.plans)
    } catch {
      /* 拦截器已 toast */
    }
  }, [])

  useEffect(() => {
    // 档位表仅 cloud 存量分支消费（订阅停售只读参考）
    if (license?.billing_mode !== 'subscription') return
    void loadPlans()
  }, [loadPlans, license?.billing_mode])

  if (license == null) {
    return (
      <section className="view flex flex-col h-full">
        <PageHeader label={t('pricing.label')} title={t('pricing.title')} />
        <div className="rule-t py-16 text-center text-sm text-dim">{t('pricing.loading')}</div>
      </section>
    )
  }

  if (isLicense) {
    return <Navigate to="/settings" replace />
  }

  return (
    <section className="view flex flex-col h-full">
      <PageHeader label={t('pricing.label')} title={t('pricing.title')} />

      {/* ================= cloud 存量：停售公告 + 配额参考（只读） ================= */}
      <div className="rule-t">
        <div className="px-8 py-6 border-b border-line" style={{ background: 'var(--bg2)' }}>
          <div className="label" style={{ color: 'var(--warn)' }}>
            {t('pricing.sunsetTitle')}
          </div>
          <div className="text-sm mt-2 text-muted leading-relaxed max-w-[720px]">
            {t('pricing.sunsetDesc')}
          </div>
        </div>
        <div className="label px-8 pt-6">{t('pricing.plansRefTitle')}</div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4">
          {plans.map((p) => {
            const current = p.current || user?.plan === p.code
            return (
              <div
                key={p.code}
                className={`border-r px-7 py-8 ${current ? 'border-acc bg-bg-2' : 'border-line'}`}
              >
                <div className="label">{planLabel(p.code)}</div>
                <div className="text-xs mt-3 num text-dim">
                  {p.price_monthly != null ? `${usd2(p.price_monthly)}/mo` : t('pricing.planRef')}
                </div>
                <ul className="mt-5 space-y-2.5 text-sm text-muted">
                  {p.features.map((f) => (
                    <li key={f}>· {f}</li>
                  ))}
                  {p.monthly_credits != null && (
                    <li>
                      · {t('pricing.monthlyCredits.pre')}{' '}
                      <span className="num">{formatNum(p.monthly_credits)}</span>{' '}
                      {t('pricing.monthlyCredits.post')}
                    </li>
                  )}
                </ul>
                {current && (
                  <div className="badge badge-solid mt-6">{t('pricing.planRef')}</div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* 积分流水（cloud=余额账本；余额列语义保留） */}
      <div className="rule-t px-8 py-4 tx-rows">
        <div className="label mb-3">{t('pricing.tx.title')}</div>
        <UsageRecords showBalance />
      </div>

      {/* 开放 API（FR-19 β）——SaaS 账户档位口径 */}
      <ApiKeysCard />
    </section>
  )
}
