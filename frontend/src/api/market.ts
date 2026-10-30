/**
 * 作品市场 API（V2-c，契约 §11）。
 * F-FE-08：从 MarketView 组件内联请求收敛到 api/ 分层。
 */
import { apiDelete, apiGet, apiPost } from './client'
import type { MarketListingInfo, MarketOrderInfo } from '../types/api'

/** GET /market/listings —— 在售列表（公开浏览） */
export function listMarketListings(params?: {
  page?: number
  page_size?: number
}): Promise<{ items: MarketListingInfo[] }> {
  return apiGet('/market/listings', params)
}

/** GET /market/my/listings —— 我的上架 */
export function listMyMarketListings(): Promise<{ items: MarketListingInfo[] }> {
  return apiGet('/market/my/listings')
}

/** GET /market/my/orders —— 我的购买订单 */
export function listMyMarketOrders(): Promise<{ items: MarketOrderInfo[] }> {
  return apiGet('/market/my/orders')
}

/** POST /market/listings —— 上架作品（确认持有商用授权） */
export function createMarketListing(req: {
  work_id: string
  price_credits: number
}): Promise<MarketListingInfo> {
  return apiPost('/market/listings', req)
}

/** DELETE /market/listings/{id} —— 下架 */
export function delistMarketListing(listingId: string): Promise<MarketListingInfo> {
  return apiDelete(`/market/listings/${listingId}`)
}

/** POST /market/listings/{id}/purchase —— 购买（原子扣积分，90/10 分账） */
export function purchaseListing(listingId: string): Promise<MarketOrderInfo> {
  return apiPost(`/market/listings/${listingId}/purchase`)
}
