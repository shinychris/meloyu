import { useCallback, useEffect, useState } from 'react'
import type { CreditTransaction, PlanInfo } from '../types/api'
import { getCreditTransactions, getPlans } from '../api/account'
import { activateLicense, activateLicenseOnline, deactivateLicense } from '../api/license'
import { useSessionStore } from '../stores/session'
import { toast } from '../stores/toast'
import { creditReasonLabel, formatDateTime, formatNum, planLabel } from '../lib/format'
import { LICENSE_SKU } from '../lib/landing-data'
import ApiKeysCard from '../components/pricing/ApiKeysCard'
import Pagination from '../components/common/Pagination'
import { PageHeader } from '../components/common/PageHeader'
import { useT } from '../i18n'

const PAGE_SIZE = 10
/** 官网购买入口（P3 License Portal 就绪前的唯一购买通道） */
const BUY_URL = 'https://meloyu.com'

/** 美分 → $ 展示（价格单一事实源：后端下发/前端 LICENSE_SKU 同源） */
const usd = (cents: number | null | undefined): string | null =>
  cents == null ? null : `$${(cents / 100).toFixed(0)}`

const usd2 = (cents: number | null | undefined): string | null =>
  cents == null ? null : `$${(cents / 100).toFixed(2)}`

/**
 * 定价与激活（v0.16.0 买断制）：
 * - license 模式（desktop/enterprise）：试用状态卡 + 终身授权买断卡 +
 *   License Key 激活表单 + 用量记录；
 * - cloud 模式（存量过渡）：订阅停售公告 + 档位配额参考（只读）+ 用量记录。
 */
export default function PricingView() {
  const [plans, setPlans] = useState<PlanInfo[]>([])
  const [txs, setTxs] = useState<CreditTransaction[]>([])
  const [txPage, setTxPage] = useState(1)
  const [txTotalPages, setTxTotalPages] = useState(1)
  const [keyInput, setKeyInput] = useState('')
  const [accountInput, setAccountInput] = useState('')
  const [codeInput, setCodeInput] = useState('')
  const [activating, setActivating] = useState(false)
  const [onlineActivating, setOnlineActivating] = useState(false)
  const [deactivating, setDeactivating] = useState(false)
  const { user, license, refreshLicense } = useSessionStore()
  const t = useT()

  const isLicense = license?.billing_mode === 'license'
  const activated = license?.activated ?? false

  const loadPlans = useCallback(async () => {
    try {
      const res = await getPlans()
      setPlans(res.plans)
    } catch {
      /* 拦截器已 toast */
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

  /** 激活：POST /licenses/activate（Ed25519 本地验签；40202 由拦截器 toast） */
  const onActivate = async () => {
    if (activating) return
    const key = keyInput.trim()
    if (!key) return
    setActivating(true)
    try {
      await activateLicense(key)
      await refreshLicense()
      setKeyInput('')
      toast(t('license.activate.done'))
    } catch {
      /* 拦截器已 toast（40202 无效 Key / 40901 未配公钥） */
    } finally {
      setActivating(false)
    }
  }

  /** 在线激活（主流程）：账户+激活码 → portal 兑换 → 本地验签落态。
   *  失败（40202 无效码/账户不符/设备满额、40901 网络不可达）由拦截器 toast */
  const onActivateOnline = async () => {
    if (onlineActivating) return
    if (!accountInput.trim() || !codeInput.trim()) return
    setOnlineActivating(true)
    try {
      await activateLicenseOnline(accountInput.trim(), codeInput.trim())
      await refreshLicense()
      setAccountInput('')
      setCodeInput('')
      toast(t('license.online.done'))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setOnlineActivating(false)
    }
  }

  /** 解除激活：保留试用记录，到期后闸门接管 */
  const onDeactivate = async () => {
    if (deactivating) return
    setDeactivating(true)
    try {
      await deactivateLicense()
      await refreshLicense()
      toast(t('license.activate.deactivated'))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setDeactivating(false)
    }
  }

  return (
    <section className="view flex flex-col h-full">
      <PageHeader label={t('pricing.label')} title={t('pricing.title')} />

      {license == null ? (
        <div className="rule-t py-16 text-center text-sm text-dim">{t('pricing.loading')}</div>
      ) : isLicense ? (
        /* ================= license 模式：状态 + 买断 + 激活 ================= */
        <div className="rule-t">
          {/* 授权状态卡 */}
          <div className="px-8 py-6 border-b border-line">
            {activated ? (
              <div className="flex items-start justify-between gap-6 flex-wrap">
                <div>
                  <div className="flex items-center gap-3">
                    <div className="label" style={{ color: 'var(--acc)' }}>
                      {t('license.status.title')}
                    </div>
                    <span className="badge badge-solid">{t('license.status.active')}</span>
                  </div>
                  <div className="text-sm mt-3 text-muted">
                    {license.license?.tier === 'enterprise'
                      ? t('license.status.tier.enterprise')
                      : t('license.status.tier.lifetime')}
                    {' · '}
                    {t('pricing.buy.oneTime')}
                  </div>
                  <div className="text-xs mt-2 num text-dim flex gap-6 flex-wrap">
                    {license.license?.account && (
                      <span>
                        {t('license.status.note')}: {license.license.account}
                      </span>
                    )}
                    <span>
                      {t('license.status.licenseId')}: {license.license?.license_id?.slice(0, 12) ?? '—'}
                    </span>
                    {license.license?.activated_at && (
                      <span>
                        {t('license.status.activatedAt')}: {formatDateTime(license.license.activated_at)}
                      </span>
                    )}
                    <span>Device: {license.device_id.slice(0, 12)}</span>
                  </div>
                </div>
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={deactivating}
                  onClick={() => void onDeactivate()}
                >
                  {deactivating
                    ? t('license.activate.deactivating')
                    : t('license.activate.deactivate')}
                </button>
              </div>
            ) : license.trial.expired ? (
              <div className="border border-bad/60 px-5 py-4" style={{ background: 'var(--bg2)' }}>
                <div className="label" style={{ color: 'var(--bad)' }}>
                  {t('license.trial.expiredTitle')}
                </div>
                <div className="text-sm mt-2 text-muted leading-relaxed">
                  {t('license.trial.expiredDesc')}
                </div>
              </div>
            ) : (
              <div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="label">{t('license.trial.title')}</div>
                    <span className="badge">{t('license.sidebar.trial')}</span>
                  </div>
                  <span className="text-xs num text-muted">
                    {t('license.trial.daysLeft', {
                      n: String(license.trial.days_left ?? 0),
                    })}
                  </span>
                </div>
                <div className="text-xs mt-2 text-dim">{t('license.trial.desc')}</div>
                <div className="h-[3px] mt-3 bg-bg-3 max-w-[420px]">
                  <div
                    className="h-full bg-acc"
                    style={{
                      width: `${Math.min(100, Math.max(3, ((license.trial.days_left ?? 0) / Math.max(1, license.trial.days)) * 100))}%`,
                    }}
                  ></div>
                </div>
              </div>
            )}
          </div>

          {/* 买断卡 + 激活表单 */}
          <div className="grid grid-cols-1 md:grid-cols-2">
            <div className="p-8 border-b md:border-b-0 md:border-r border-line relative">
              <div className="badge badge-solid absolute top-6 right-8">
                {t('pricing.buy.badge')}
              </div>
              <div className="label" style={{ color: 'var(--acc)' }}>
                {t(LICENSE_SKU.name)}
              </div>
              <div className="price-num mt-4 flex items-baseline gap-3 flex-wrap">
                <span>{usd(license.sale_price_usd)}</span>
                <span className="text-base font-bold text-dim line-through">
                  {usd(license.price_usd)}
                </span>
                <span className="text-base font-bold text-muted">
                  {t('pricing.buy.oneTime')}
                </span>
              </div>
              <div className="text-xs mt-1.5 text-dim">
                {t(LICENSE_SKU.tagline)} · {t(LICENSE_SKU.platforms)}
              </div>
              <ul className="mt-5 space-y-2 text-sm text-muted">
                {LICENSE_SKU.features.map((f) => (
                  <li key={f}>
                    <span style={{ color: 'var(--acc)' }}>· </span>
                    {t(f)}
                  </li>
                ))}
              </ul>
              <a
                className="btn btn-acc w-full mt-6 block text-center"
                href={BUY_URL}
                target="_blank"
                rel="noreferrer"
              >
                {t('pricing.buy.cta')}
              </a>
              <div className="text-xs mt-3 text-dim leading-relaxed">
                {t('pricing.buy.note')}
                <br />
                {t('pricing.buy.enterprise')}
              </div>
            </div>

            <div className="p-8">
              <div className="label">{t('license.activate.label')}</div>
              <div className="text-md font-bold mt-2">{t('license.online.title')}</div>
              <div className="text-xs mt-2 leading-relaxed max-w-[460px] text-dim">
                {t('license.online.desc')}
              </div>
              {/* 在线激活（主流程）：账户 + 激活码 */}
              <div className="mt-4 max-w-[460px] space-y-3">
                <div>
                  <div className="text-2xs mb-1 text-muted">{t('license.online.accountLabel')}</div>
                  <input
                    className="input w-full"
                    type="email"
                    autoComplete="email"
                    value={accountInput}
                    placeholder={t('license.online.accountPlaceholder')}
                    onChange={(e) => setAccountInput(e.target.value)}
                  />
                </div>
                <div>
                  <div className="text-2xs mb-1 text-muted">{t('license.online.codeLabel')}</div>
                  <input
                    className="input w-full num"
                    style={{ textTransform: 'uppercase' }}
                    spellCheck={false}
                    value={codeInput}
                    placeholder={t('license.online.codePlaceholder')}
                    onChange={(e) => setCodeInput(e.target.value)}
                  />
                </div>
                <button
                  className="btn btn-acc w-full"
                  disabled={onlineActivating || !accountInput.trim() || !codeInput.trim()}
                  onClick={() => void onActivateOnline()}
                >
                  {onlineActivating ? t('license.online.doing') : t('license.online.cta')}
                </button>
              </div>
              {/* 离线激活（备用）：完整授权密钥 */}
              <details className="mt-5 max-w-[460px]">
                <summary className="text-2xs cursor-pointer text-dim hover:text-muted select-none">
                  {t('license.offline.fold')}
                </summary>
                <div className="text-xs mt-2 leading-relaxed text-dim">
                  {t('license.activate.desc')}
                </div>
                <textarea
                  className="input mt-2 w-full num"
                  style={{ minHeight: 72 }}
                  spellCheck={false}
                  value={keyInput}
                  placeholder={t('license.activate.placeholder')}
                  onChange={(e) => setKeyInput(e.target.value)}
                />
                <button
                  className="btn mt-2"
                  disabled={activating || !keyInput.trim()}
                  onClick={() => void onActivate()}
                >
                  {activating ? t('license.activate.activating') : t('license.activate.cta')}
                </button>
              </details>
            </div>
          </div>

          <div className="rule-t px-8 py-4 text-xs text-dim">{t('pricing.usage.footnote')}</div>
        </div>
      ) : (
        /* ================= cloud 存量：停售公告 + 配额参考（只读） ================= */
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
      )}

      {/* 用量/积分流水（license=纯计量，cloud=余额账本） */}
      <div className="rule-t px-8 py-4 tx-rows">
        <div className="label mb-3">
          {isLicense ? t('pricing.usage.title') : t('pricing.tx.title')}
        </div>
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
