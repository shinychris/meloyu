import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { MarketListingInfo, MarketOrderInfo, Work } from '../types/api'
import { apiDelete, apiGet, apiPost } from '../api/client'
import { listWorks } from '../api/works'
import { useSessionStore } from '../stores/session'
import { usePlayerStore } from '../stores/player'
import { useConfirmStore } from '../stores/confirm'
import { toast } from '../stores/toast'
import { useT } from '../i18n'
import { formatNum } from '../lib/format'

type Tab = 'browse' | 'mine' | 'orders'
const TAB_KEYS: Record<Tab, 'market.tab.browse' | 'market.tab.mine' | 'market.tab.orders'> = {
  browse: 'market.tab.browse',
  mine: 'market.tab.mine',
  orders: 'market.tab.orders',
}

/**
 * 作品市场（V2-c，v0.10.1）：浏览/购买（积分分账 90/10 + 非独占授权）+
 * 我的作品上架管理 + 发行清单（分发对接指引；发行打包走作品页发行导出 FR-11）。
 */
export default function MarketView() {
  const t = useT()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('browse')
  const [listings, setListings] = useState<MarketListingInfo[]>([])
  const [myListings, setMyListings] = useState<MarketListingInfo[]>([])
  const [orders, setOrders] = useState<MarketOrderInfo[]>([])
  const [myWorks, setMyWorks] = useState<Work[]>([])
  const [publishWorkId, setPublishWorkId] = useState('')
  const [price, setPrice] = useState(100)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const user = useSessionStore((s) => s.user)
  const refreshUser = useSessionStore((s) => s.refreshUser)
  const playTrack = usePlayerStore((s) => s.playTrack)

  const refresh = useCallback(() => {
    setLoading(true)
    Promise.allSettled([
      apiGet<{ items: MarketListingInfo[] }>('/market/listings', { page_size: 50 })
        .then((r) => setListings(r.items)),
      apiGet<{ items: MarketListingInfo[] }>('/market/my/listings')
        .then((r) => setMyListings(r.items)),
      apiGet<{ items: MarketOrderInfo[] }>('/market/my/orders')
        .then((r) => setOrders(r.items)),
      listWorks({ page_size: 50 })
        .then((r) => setMyWorks(r.items)),
    ]).finally(() => setLoading(false))
  }, [])
  useEffect(refresh, [refresh])

  const onPlay = (l: MarketListingInfo) => {
    if (!l.preview_file_id) {
      toast(t('market.toast.noPreview'), 'warn')
      return
    }
    // 试听走公开端点（免鉴权，买家验货口径）；购买后的完整访问走订单 viewer 权限
    void playTrack({
      fileId: `market:${l.id}`,
      url: `/api/v1/market/listings/${l.id}/preview`,
      title: l.title,
      subtitle: `${t('market.seller')}: ${l.seller.nickname}`,
      durationSec: 0,
    })
  }

  const onBuy = async (l: MarketListingInfo) => {
    if (busy || !user) return
    if ((user.credits.balance ?? 0) < l.price_credits) {
      toast(t('market.toast.insufficient'), 'warn')
      return
    }
    const okToBuy = await useConfirmStore.getState().confirm({
      title: t('market.confirm.buy', { title: l.title, n: l.price_credits }),
      danger: false,
    })
    if (!okToBuy) return
    setBusy(true)
    try {
      const order = await apiPost<MarketOrderInfo>(`/market/listings/${l.id}/purchase`)
      toast(t('market.toast.bought', { title: l.title }))
      void refreshUser()
      setOrders((prev) => [order, ...prev])
      setTab('orders')
    } catch {
      /* 拦截器已 toast（已购/余额不足） */
    } finally {
      setBusy(false)
    }
  }

  const onPublish = async () => {
    if (busy) return
    if (!publishWorkId) {
      toast(t('market.toast.pickWork'), 'warn')
      return
    }
    const okToPublish = await useConfirmStore.getState().confirm({
      title: t('market.confirm.ack'),
      danger: false,
    })
    if (!okToPublish) return
    setBusy(true)
    try {
      await apiPost('/market/listings', { work_id: publishWorkId, price_credits: price })
      toast(t('market.toast.published'))
      setPublishWorkId('')
      refresh()
    } catch {
      /* 拦截器已 toast（已在架等） */
    } finally {
      setBusy(false)
    }
  }

  const onDelist = async (id: string) => {
    try {
      await apiDelete(`/market/listings/${id}`)
      refresh()
    } catch {
      /* 拦截器已 toast */
    }
  }

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4">
        <div className="label">{t('market.view.label')}</div>
        <h1 className="text-[28px] font-extrabold tracking-tight mt-1">{t('market.view.headline')}</h1>
      </header>

      <div className="px-8 flex gap-1.5 flex-wrap">
        {(['browse', 'mine', 'orders'] as Tab[]).map((k) => (
          <button type="button" key={k} className={`chip ${tab === k ? 'on' : ''}`} onClick={() => setTab(k)}>
            {t(TAB_KEYS[k])}
          </button>
        ))}
      </div>

      <div className="rule-t flex-1 min-h-0 overflow-y-auto px-8 py-5">
        {loading ? (
          <div className="text-[12px] py-16 text-center" style={{ color: 'var(--dim)' }}>
            {t('common.loading')}
          </div>
        ) : tab === 'browse' && (
          <>
            <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3" data-testid="market-grid">
              {listings.length === 0 ? (
                <div className="py-16 text-center text-[12px] col-span-full" style={{ color: 'var(--dim)' }}>
                  {t('market.empty.browse')}
                </div>
              ) : (
                listings.map((l) => (
                  <div key={l.id} className="card p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-[13px] font-bold truncate">{l.title}</div>
                        <div className="text-[10px] mt-0.5" style={{ color: 'var(--dim)' }}>
                          {t('market.seller')}: {l.seller.nickname} · {t('market.sales', { n: l.sales })}
                        </div>
                      </div>
                      <span className="text-[12px] num font-bold shrink-0" style={{ color: 'var(--acc)' }}>
                        {formatNum(l.price_credits)}
                      </span>
                    </div>
                    {l.tags.length > 0 && (
                      <div className="flex gap-1 mt-2 flex-wrap">
                        {l.tags.slice(0, 4).map((tg) => (
                          <span key={tg} className="text-[9px] px-1.5 py-0.5" style={{ background: 'var(--bg3)', color: 'var(--muted)' }}>
                            {tg}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="flex gap-2 mt-3">
                      <button className="btn btn-ghost !py-1 !px-2.5 text-[10px]" onClick={() => onPlay(l)}>
                        ▶ {t('market.preview')}
                      </button>
                      {user && l.seller.user_id !== user.id && (
                        <button className="btn btn-acc !py-1 !px-2.5 text-[10px] flex-1" disabled={busy} onClick={() => void onBuy(l)}>
                          {t('market.buy', { n: formatNum(l.price_credits) })}
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
            <div className="card p-4 mt-4" data-testid="distro-checklist">
              <div className="label mb-2">{t('market.distro.title')}</div>
              <ul className="text-[11px] leading-relaxed list-disc pl-5 space-y-1" style={{ color: 'var(--muted)' }}>
                <li>{t('market.distro.step1')}</li>
                <li>{t('market.distro.step2')}</li>
                <li>{t('market.distro.step3')}</li>
              </ul>
            </div>
          </>
        )}

        {tab === 'mine' && (
          <>
            <div className="card p-4">
              <div className="label mb-2">{t('market.publish.title')}</div>
              <div className="text-[10px] mb-2 leading-relaxed" style={{ color: 'var(--dim)' }}>
                {t('market.publish.ack')}
              </div>
              <div className="flex gap-2 flex-wrap">
                <select className="!text-[11px]" value={publishWorkId} onChange={(e) => setPublishWorkId(e.target.value)}>
                  <option value="">{t('market.publish.pick')}</option>
                  {myWorks.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.display_code} · {w.title}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  min={1}
                  max={100000}
                  className="!text-[11px] w-24 num"
                  value={price}
                  onChange={(e) => setPrice(Number(e.target.value))}
                  title={t('market.publish.price')}
                />
                <button className="btn btn-acc !py-1.5 !px-3 text-[11px]" disabled={busy} onClick={() => void onPublish()}>
                  {t('market.publish.run')}
                </button>
              </div>
            </div>
            <div className="mt-4 space-y-2">
              {myListings.length === 0 ? (
                <div className="py-10 text-center text-[12px]" style={{ color: 'var(--dim)' }}>
                  {t('market.empty.mine')}
                </div>
              ) : (
                myListings.map((l) => (
                  <div key={l.id} className="card p-3 flex items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-[12px] font-semibold truncate">{l.title}</div>
                      <div className="text-[10px] mt-0.5" style={{ color: 'var(--dim)' }}>
                        {l.status === 'active' ? t('market.status.active') : t('market.status.delisted')} ·{' '}
                        {t('market.sales', { n: l.sales })} · {formatNum(l.price_credits)} {t('market.credits')}
                      </div>
                    </div>
                    {l.status === 'active' && (
                      <button className="btn btn-ghost !py-1 !px-2 text-[10px]" onClick={() => void onDelist(l.id)}>
                        {t('market.delist')}
                      </button>
                    )}
                    <button className="btn btn-ghost !py-1 !px-2 text-[10px]" onClick={() => navigate(`/works/${l.work_id}`)}>
                      {t('market.openWork')}
                    </button>
                  </div>
                ))
              )}
            </div>
          </>
        )}

        {tab === 'orders' && (
          <div className="space-y-2">
            {orders.length === 0 ? (
              <div className="py-16 text-center text-[12px]" style={{ color: 'var(--dim)' }}>
                {t('market.empty.orders')}
              </div>
            ) : (
              orders.map((o) => (
                <div key={o.id} className="card p-3">
                  <div className="flex items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-[12px] font-semibold">
                        {t('market.order.no', { id: o.id.slice(0, 8) })} · {formatNum(o.price_credits)} {t('market.credits')}
                      </div>
                      <div className="text-[10px] mt-0.5 num" style={{ color: 'var(--dim)' }}>
                        {o.created_at.slice(0, 16).replace('T', ' ')}
                      </div>
                    </div>
                    <button className="btn btn-ghost !py-1 !px-2 text-[10px]" onClick={() => navigate(`/works/${o.work_id}`)}>
                      {t('market.openWork')}
                    </button>
                  </div>
                  <div className="text-[9px] mt-2 leading-relaxed" style={{ color: 'var(--dim)' }}>
                    {o.license}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </section>
  )
}
