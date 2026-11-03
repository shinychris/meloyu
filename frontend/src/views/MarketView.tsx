import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { MarketListingInfo, MarketOrderInfo, Work } from '../types/api'
import {
  createMarketListing,
  delistMarketListing,
  listMarketListings,
  listMyMarketListings,
  listMyMarketOrders,
  purchaseListing,
} from '../api/market'
import { listWorks } from '../api/works'
import { useSessionStore } from '../stores/session'
import { usePlayerStore } from '../stores/player'
import { useConfirmStore } from '../stores/confirm'
import { toast } from '../stores/toast'
import { useT } from '../i18n'
import { formatNum } from '../lib/format'
import { PageHeader } from '../components/common/PageHeader'
import { EmptyState } from '../components/common/EmptyState'

type Tab = 'browse' | 'mine' | 'orders'
const TAB_KEYS: Record<Tab, 'market.tab.browse' | 'market.tab.mine' | 'market.tab.orders'> = {
  browse: 'market.tab.browse',
  mine: 'market.tab.mine',
  orders: 'market.tab.orders',
}

/**
 * 作品市场（v0.10.1）：浏览/购买（积分分账 90/10 + 非独占授权）+
 * 我的作品上架管理 + 发行清单（分发对接指引；发行打包走作品页发行导出）。
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
      listMarketListings({ page_size: 50 })
        .then((r) => setListings(r.items)),
      listMyMarketListings()
        .then((r) => setMyListings(r.items)),
      listMyMarketOrders()
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
      const order = await purchaseListing(l.id)
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
      await createMarketListing({ work_id: publishWorkId, price_credits: price })
      toast(t('market.toast.published'))
      setPublishWorkId('')
      refresh()
    } catch {
      /* 拦截器已 toast（已在架等） */
    } finally {
      setBusy(false)
    }
  }

  const onDelist = async (l: MarketListingInfo) => {
    // ：下架为破坏性操作（买家不可再购），二次确认
    const ok = await useConfirmStore.getState().confirm({
      title: t('market.confirm.delistTitle', { title: l.title }),
      description: t('market.confirm.delistDesc'),
      confirmText: t('market.delist'),
      danger: true,
    })
    if (!ok) return
    try {
      await delistMarketListing(l.id)
      refresh()
    } catch {
      /* 拦截器已 toast */
    }
  }

  return (
    <section className="view flex flex-col h-full">
      <PageHeader label={t('market.view.label')} title={t('market.view.headline')}>
        <div className="mt-4 flex gap-1.5 flex-wrap">
          {(['browse', 'mine', 'orders'] as Tab[]).map((k) => (
            <button type="button" key={k} className={`chip ${tab === k ? 'on' : ''}`} onClick={() => setTab(k)}>
              {t(TAB_KEYS[k])}
            </button>
          ))}
        </div>
      </PageHeader>

      <div className="rule-t flex-1 min-h-0 overflow-y-auto px-8 py-5">
        {loading ? (
          <div className="text-sm py-16 text-center text-dim">{t('common.loading')}</div>
        ) : tab === 'browse' && (
          <>
            <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3" data-testid="market-grid">
              {listings.length === 0 ? (
                <EmptyState compact className="col-span-full" title={t('market.empty.browse')} />
              ) : (
                listings.map((l) => (
                  <div key={l.id} className="card p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-base font-bold truncate">{l.title}</div>
                        <div className="text-2xs mt-0.5 text-dim">
                          {t('market.seller')}: {l.seller.nickname} · {t('market.sales', { n: l.sales })}
                        </div>
                      </div>
                      <span className="text-sm num font-bold shrink-0 text-acc">{formatNum(l.price_credits)}</span>
                    </div>
                    {l.tags.length > 0 && (
                      <div className="flex gap-1 mt-2 flex-wrap">
                        {l.tags.slice(0, 4).map((tg) => (
                          <span key={tg} className="badge">
                            {tg}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="flex gap-2 mt-3">
                      <button className="btn btn-ghost btn-sm" onClick={() => onPlay(l)}>
                        ▶ {t('market.preview')}
                      </button>
                      {user && l.seller.user_id !== user.id && (
                        <button className="btn btn-acc btn-sm flex-1" disabled={busy} onClick={() => void onBuy(l)}>
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
              <ul className="text-xs leading-relaxed list-disc pl-5 space-y-1 text-muted">
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
              <div className="text-2xs mb-2 leading-relaxed text-dim">{t('market.publish.ack')}</div>
              <div className="flex gap-2 flex-wrap">
                <select className="text-xs" value={publishWorkId} onChange={(e) => setPublishWorkId(e.target.value)}>
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
                  className="text-xs w-24 num"
                  value={price}
                  onChange={(e) => setPrice(Number(e.target.value))}
                  title={t('market.publish.price')}
                />
                <button className="btn btn-acc btn-sm" disabled={busy} onClick={() => void onPublish()}>
                  {t('market.publish.run')}
                </button>
              </div>
            </div>
            <div className="mt-4 space-y-2">
              {myListings.length === 0 ? (
                <EmptyState compact title={t('market.empty.mine')} />
              ) : (
                myListings.map((l) => (
                  <div key={l.id} className="card p-3 flex items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold truncate">{l.title}</div>
                      <div className="text-2xs mt-0.5 text-dim">
                        {l.status === 'active' ? t('market.status.active') : t('market.status.delisted')} ·{' '}
                        {t('market.sales', { n: l.sales })} · {formatNum(l.price_credits)} {t('market.credits')}
                      </div>
                    </div>
                    {l.status === 'active' && (
                      <button className="btn btn-ghost btn-sm" onClick={() => void onDelist(l)}>
                        {t('market.delist')}
                      </button>
                    )}
                    <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/works/${l.work_id}`)}>
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
              <EmptyState compact title={t('market.empty.orders')} />
            ) : (
              orders.map((o) => (
                <div key={o.id} className="card p-3">
                  <div className="flex items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold">
                        {t('market.order.no', { id: o.id.slice(0, 8) })} · {formatNum(o.price_credits)} {t('market.credits')}
                      </div>
                      <div className="text-2xs mt-0.5 num text-dim">{o.created_at.slice(0, 16).replace('T', ' ')}</div>
                    </div>
                    <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/works/${o.work_id}`)}>
                      {t('market.openWork')}
                    </button>
                  </div>
                  <div className="text-2xs mt-2 leading-relaxed text-dim">{o.license}</div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </section>
  )
}
