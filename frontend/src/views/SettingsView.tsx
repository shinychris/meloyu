import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { UsageStats } from '../types/api'
import { getUsageStats } from '../api/usage'
import { activateLicense, activateLicenseOnline, deactivateLicense } from '../api/license'
import { exportData } from '../api/auth'
import { saveBlob } from '../api/client'
import { useSessionStore } from '../stores/session'
import { useMetaStore } from '../stores/meta'
import { toast } from '../stores/toast'
import { formatDateTime, formatNum } from '../lib/format'
import { useScrollSpy } from '../lib/useScrollSpy'
import { LICENSE_SKU } from '../lib/landing-data'
import { SITE_URL } from '../lib/constants'
import UsageRecords from '../components/settings/UsageRecords'
import { useI18nStore, useT, type TranslationKey } from '../i18n'
import type { Locale } from '../i18n'


/** 美分 → $ 展示（价格单一事实源：后端下发/前端 LICENSE_SKU 同源） */
const usd = (cents: number | null | undefined): string | null =>
  cents == null ? null : `$${(cents / 100).toFixed(0)}`

/** 引擎通道 → 展示名（复用模型中心通道词条；未知通道回退原始标识）。
 *  localsynth=歌曲离线合成引擎（用量统计的歌曲通道维度）；none=歌词引擎未配置 */
const ENGINE_LABEL: Record<string, TranslationKey> = {
  localsynth: 'models.mbackend.localsynth.title',
  none: 'models.backend.none.title',
  ollama: 'models.backend.ollama.title',
  openai_compat: 'models.backend.openai_compat.title',
  api: 'models.mbackend.api.title',
  replicate: 'models.mbackend.replicate.title',
  musicgen_local: 'models.mbackend.musicgen_local.title',
  acestep_local: 'models.mbackend.acestep_local.title',
  mmax_local: 'models.mbackend.mmax_local.title',
  songgen_local: 'models.mbackend.songgen_local.title',
}

const LANG_NAME: Record<Locale, TranslationKey> = {
  en: 'common.lang.en',
  zh: 'common.lang.zh',
}

/** 引擎通道展示名（词条命中则本地化，未知通道回退原始标识） */
function engineLabel(engine: string, t: (k: TranslationKey) => string): string {
  const key = ENGINE_LABEL[engine]
  return key ? t(key) : engine
}

/** 左侧分区导航（锚点 + scrollspy 高亮，模式对齐模型中心） */
const SECTIONS: { id: string; labelKey: TranslationKey }[] = [
  { id: 'set-general', labelKey: 'settings.nav.general' },
  { id: 'set-usage', labelKey: 'settings.nav.usage' },
  { id: 'set-license', labelKey: 'settings.nav.license' },
  { id: 'set-engines', labelKey: 'settings.nav.engines' },
]

const USAGE_WINDOW_DAYS = 30

/** 桌面壳桥（Electron preload 注入）；裸浏览器/SSR 为 undefined */
const desktopShell =
  typeof window !== 'undefined' ? window.meloyuDesktop : undefined

/**
 * 系统设置（v0.17.0）：license（桌面买断）形态的统一设置页——
 * 通用（语言/应用信息/数据管理）、用量统计与分析（用户自定义 API 口径，
 * 无官方积分消耗）、授权与激活（自定价页迁入）、引擎与 API 快捷入口。
 * cloud 存量形态由路由守卫回定价页（本视图不可达）。
 */
export default function SettingsView() {
  const navigate = useNavigate()
  const t = useT()
  const setLocale = useI18nStore((s) => s.setLocale)
  const locale = useI18nStore((s) => s.locale)
  const meta = useMetaStore((s) => s.meta)
  const { license, refreshLicense } = useSessionStore()

  const [stats, setStats] = useState<UsageStats | null>(null)
  const [keyInput, setKeyInput] = useState('')
  const [accountInput, setAccountInput] = useState('')
  const [codeInput, setCodeInput] = useState('')
  const [activating, setActivating] = useState(false)
  const [onlineActivating, setOnlineActivating] = useState(false)
  const [deactivating, setDeactivating] = useState(false)
  const [exporting, setExporting] = useState(false)

  // scrollspy（F-FE-09 抽取共用 hook，与模型中心同源）：分区进入滚动视口上部
  // 区域时高亮导航项（SSR/测试环境无 IO，防御跳过）
  const { scrollRef, activeSection } = useScrollSpy(
    SECTIONS.map((s) => s.id),
    '-15% 0px -70% 0px',
  )

  const jump = useCallback((id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  useEffect(() => {
    void getUsageStats(USAGE_WINDOW_DAYS)
      .then(setStats)
      .catch(() => {
        /* 拦截器已 toast */
      })
  }, [])

  const activated = license?.activated ?? false
  const daysLeft = license?.trial.days_left ?? 0
  // 折扣支持（v0.17.0 定价调整）：成交价低于原价时展示折扣百分比与划线原价；
  // sale ≥ price 或非正 = 无折扣 → 单价格局（env 改价即可开关折扣）
  const discountPct =
    license && license.price_usd > license.sale_price_usd && license.sale_price_usd > 0
      ? Math.round(((license.price_usd - license.sale_price_usd) / license.price_usd) * 100)
      : null

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

  /** 在线激活（主流程）：账户+激活码 → portal 兑换 → 本地验签落态 */
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

  /** 导出我的数据：GET /auth/export-data（zip 流）→ a[download] 保存 */
  const onExport = async () => {
    if (exporting) return
    setExporting(true)
    toast(t('auth.export.preparing'))
    try {
      const blob = await exportData()
      saveBlob(blob, `meloyu-data-export-${new Date().toISOString().slice(0, 10)}.zip`)
      toast(t('auth.export.started'))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setExporting(false)
    }
  }

  const win = stats?.totals.window
  const allTime = stats?.totals.all_time
  const successRate = win && win.calls > 0 ? Math.round((win.succeeded / win.calls) * 100) : null
  const maxUnits = Math.max(1, ...(stats?.by_day.map((d) => d.units) ?? [0]))
  const editionKey: TranslationKey =
    license?.mode === 'enterprise'
      ? 'settings.general.edition.enterprise'
      : license?.mode === 'desktop'
        ? 'settings.general.edition.desktop'
        : 'settings.general.edition.cloud'

  const summaryCards = [
    { labelKey: 'settings.usage.card.calls', value: formatNum(win?.calls ?? 0) },
    { labelKey: 'settings.usage.card.units', value: formatNum(win?.units ?? 0) },
    { labelKey: 'settings.usage.card.successRate', value: successRate == null ? '—' : `${successRate}%` },
    { labelKey: 'settings.usage.card.remoteCalls', value: formatNum(stats?.remote_api_calls ?? 0) },
  ] as const

  return (
    <div className="view h-full overflow-y-auto" ref={scrollRef}>
      <div className="px-4 md:px-8 py-8">
        <div className="label">{t('settings.label')}</div>
        <h1 className="text-3xl font-extrabold tracking-tight mt-2">{t('settings.title')}</h1>

        <div className="flex items-start gap-8 mt-6">
          {/* 左侧分区导航 */}
          <aside className="w-[168px] flex-none sticky top-6 hidden lg:block">
            <div className="py-1">
              {SECTIONS.map((s) => {
                const active = activeSection === s.id
                return (
                  <button
                    key={s.id}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors flex items-center gap-2 border-l-2 ${
                      active ? 'text-acc font-bold bg-bg-2 border-acc' : 'text-muted font-normal border-transparent'
                    }`}
                    onClick={() => jump(s.id)}
                  >
                    {t(s.labelKey)}
                  </button>
                )
              })}
            </div>
          </aside>

          <div className="flex-1 min-w-0">
            {/* ============ 通用 ============ */}
            <section id="set-general" className="scroll-mt-4">
              <div className="label mb-3">{t('settings.nav.general')}</div>

              {/* 语言 */}
              <div className="card p-5">
                <div className="text-base font-bold">{t('settings.general.language')}</div>
                <div className="flex gap-2 mt-3">
                  {(['zh', 'en'] as const).map((l) => (
                    <button
                      key={l}
                      className={`chip ${locale === l ? 'on' : ''}`}
                      aria-pressed={locale === l}
                      onClick={() => setLocale(l)}
                    >
                      {t(LANG_NAME[l])}
                    </button>
                  ))}
                </div>
              </div>

              {/* 应用信息 */}
              <div className="card p-5 mt-4">
                <div className="text-base font-bold">{t('settings.general.appInfo')}</div>
                <div className="mt-3 space-y-2 text-sm text-muted">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="text-dim text-xs w-28 flex-none">{t('settings.general.edition')}</span>
                    <span className="badge badge-solid">{t(editionKey)}</span>
                  </div>
                  {desktopShell && (
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="text-dim text-xs w-28 flex-none">{t('settings.general.version')}</span>
                      <span className="text-xs num">
                        Electron {desktopShell.versions.electron} · Chromium{' '}
                        {desktopShell.versions.chrome}
                      </span>
                    </div>
                  )}
                  {meta.data_dir && (
                    <div className="flex items-start gap-3 flex-wrap">
                      <span className="text-dim text-xs w-28 flex-none pt-0.5">{t('settings.general.dataDir')}</span>
                      <div className="min-w-0">
                        <div className="text-xs num break-all">{meta.data_dir}</div>
                        <div className="text-2xs text-dim mt-1">{t('settings.general.dataDirNote')}</div>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* 数据管理 */}
              <div className="card p-5 mt-4">
                <div className="text-base font-bold">{t('settings.general.data')}</div>
                <button
                  className="btn btn-sm mt-3"
                  disabled={exporting}
                  onClick={() => void onExport()}
                >
                  {exporting ? t('auth.export.preparing') : t('auth.menu.exportData')}
                </button>
              </div>
            </section>

            {/* ============ 用量统计与分析 ============ */}
            <section id="set-usage" className="scroll-mt-4 mt-10">
              <div className="label mb-3">{t('settings.nav.usage')}</div>

              <div className="card p-5">
                <div className="text-xs leading-relaxed text-dim max-w-[720px]">
                  {t('settings.usage.desc')}
                </div>

                {/* 汇总卡片 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
                  {summaryCards.map((c) => (
                    <div key={c.labelKey} className="border border-line px-4 py-3" style={{ background: 'var(--bg2)' }}>
                      <div className="text-2xs text-dim">{t(c.labelKey)}</div>
                      <div className="text-xl font-extrabold num mt-1">{c.value}</div>
                    </div>
                  ))}
                </div>
                <div className="text-2xs mt-2 text-dim">
                  {t('settings.usage.window', { n: USAGE_WINDOW_DAYS })}
                  {' · '}
                  {t('settings.usage.allTime')}
                  {allTime
                    ? `: ${formatNum(allTime.calls)} · ${formatNum(allTime.units)}`
                    : ''}
                </div>

                {/* 每日趋势（纯 CSS 柱状；无图表库依赖） */}
                {stats && stats.by_day.length > 0 && (
                  <div className="mt-5">
                    <div className="text-xs mb-2 text-muted">{t('settings.usage.byDay')}</div>
                    <div className="flex items-end gap-[3px] h-[96px]">
                      {stats.by_day.map((d) => (
                        <div
                          key={d.date}
                          className="flex-1 min-w-[3px] bg-acc/70 hover:bg-acc transition-colors"
                          style={{ height: `${Math.max(d.units > 0 ? 6 : 2, (d.units / maxUnits) * 96)}px` }}
                          title={`${d.date} · ${d.calls} · ${d.units}`}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* 按引擎通道 */}
                <div className="mt-5">
                  <div className="text-xs mb-2 text-muted">{t('settings.usage.byEngine')}</div>
                  {stats && stats.by_engine.length > 0 ? (
                    <div className="tx-rows">
                      <div className="row !cursor-default text-dim" style={{ gridTemplateColumns: '1.5fr 170px 80px 80px 80px' }}>
                        <span className="label">{t('settings.usage.engine')}</span>
                        <span className="label">{t('settings.usage.kind')}</span>
                        <span className="label">{t('settings.usage.card.calls')}</span>
                        <span className="label">{t('settings.usage.succeeded')}</span>
                        <span className="label">{t('settings.usage.card.units')}</span>
                      </div>
                      {stats.by_engine.map((e) => (
                        <div key={e.engine} className="row !cursor-default" style={{ gridTemplateColumns: '1.5fr 170px 80px 80px 80px' }}>
                          <span className="text-sm text-txt truncate">
                            {engineLabel(e.engine, t)}
                          </span>
                          <span className={`text-xs ${e.kind === 'remote_api' ? 'text-acc' : 'text-muted'}`}>
                            {t(e.kind === 'remote_api' ? 'settings.usage.kind.remote' : 'settings.usage.kind.local')}
                          </span>
                          <span className="text-sm num text-muted">{formatNum(e.calls)}</span>
                          <span className="text-xs num text-muted">{formatNum(e.succeeded)}</span>
                          <span className="text-sm num font-semibold text-txt">{formatNum(e.units)}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs text-dim">{t('settings.usage.emptyEngine')}</div>
                  )}
                </div>

                {/* 歌词引擎调用 */}
                {stats && stats.lyrics_by_engine.length > 0 && (
                  <div className="mt-5">
                    <div className="text-xs mb-2 text-muted">{t('settings.usage.lyricsTitle')}</div>
                    <div className="flex gap-2 flex-wrap">
                      {stats.lyrics_by_engine.map((l) => (
                        <span key={l.engine} className="chip" title={l.engine}>
                          {engineLabel(l.engine, t)}
                          {' · '}
                          <span className="num">{formatNum(l.calls)}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* 用量记录（license=纯计量，无余额列） */}
              <div className="rule-t mt-4 px-0 py-2">
                <div className="label mb-3">{t('pricing.usage.title')}</div>
                <UsageRecords showBalance={false} />
                <div className="text-2xs mt-3 text-dim">{t('pricing.usage.footnote')}</div>
              </div>
            </section>

            {/* ============ 授权与激活 ============ */}
            <section id="set-license" className="scroll-mt-4 mt-10">
              <div className="label mb-3">{t('settings.nav.license')}</div>

              {/* 授权状态卡 */}
              <div className="card p-5">
                {license == null ? (
                  <div className="text-sm text-dim py-4 text-center">{t('settings.loading')}</div>
                ) : activated ? (
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
                        <span>{t('license.status.device')}: {license.device_id.slice(0, 12)}</span>                      </div>
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
                        {t('license.trial.daysLeft', { n: String(daysLeft) })}
                      </span>
                    </div>
                    <div className="text-xs mt-2 text-dim">{t('license.trial.desc')}</div>
                    <div className="h-[3px] mt-3 bg-bg-3 max-w-[420px]">
                      <div
                        className="h-full bg-acc"
                        style={{
                          width: `${Math.min(100, Math.max(3, (daysLeft / Math.max(1, license.trial.days)) * 100))}%`,
                        }}
                      ></div>
                    </div>
                  </div>
                )}
              </div>

              {/* 买断卡 + 激活表单（未激活时展示） */}
              {license != null && !activated && (
                <div className="grid grid-cols-1 md:grid-cols-2 mt-4">
                  <div className="card p-6 relative">
                    {discountPct != null && (
                      <div className="badge badge-solid absolute top-5 right-6">
                        {t('pricing.buy.badge')} · -{discountPct}%
                      </div>
                    )}
                    <div className="label" style={{ color: 'var(--acc)' }}>
                      {t(LICENSE_SKU.name)}
                    </div>
                    <div className="price-num mt-3 flex items-baseline gap-3 flex-wrap">
                      <span>{usd(license.sale_price_usd)}</span>
                      {discountPct != null && (
                        <span className="text-base font-bold text-dim line-through">
                          {usd(license.price_usd)}
                        </span>
                      )}
                      <span className="text-base font-bold text-muted">
                        {t('pricing.buy.oneTime')}
                      </span>
                    </div>
                    <div className="text-xs mt-1.5 text-dim">
                      {t(LICENSE_SKU.tagline)} · {t(LICENSE_SKU.platforms)}
                    </div>
                    <ul className="mt-4 space-y-2 text-sm text-muted">
                      {LICENSE_SKU.features.map((f) => (
                        <li key={f}>
                          <span style={{ color: 'var(--acc)' }}>· </span>
                          {t(f)}
                        </li>
                      ))}
                    </ul>
                    <a
                      className="btn btn-acc w-full mt-5 block text-center"
                      href={SITE_URL}
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

                  <div className="card p-6 md:border-l-0">
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
              )}
            </section>

            {/* ============ 引擎与 API ============ */}
            <section id="set-engines" className="scroll-mt-4 mt-10 pb-8">
              <div className="label mb-3">{t('settings.nav.engines')}</div>
              <div className="card p-5 flex items-center justify-between gap-4 flex-wrap">
                <div className="text-xs text-dim max-w-[520px] leading-relaxed">
                  {t('settings.engines.desc')}
                </div>
                <button className="btn btn-sm" onClick={() => navigate('/models')}>
                  {t('settings.engines.open')}
                </button>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}
