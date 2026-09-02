import { apiGet, apiPost } from './client'
import type {
  BillingCheckoutRequest,
  BillingCheckoutResult,
  BillingOrdersResult,
  BillingPortalResult,
} from '../types/api'

/**
 * v0.7.0 计费（Stripe）：
 * - checkout 返回跳转 url（前端 window.location.href 整页跳转去 Stripe）；
 *   Stripe 未配置时后端返 40901，拦截器已 toast 后端 message，调用方静默即可。
 * - portal 为 Stripe 客户门户，无支付记录时后端同样返 40901。
 */

/** POST /billing/checkout —— 发起订阅（pro/studio × monthly/yearly）或充值积分包 */
export function checkout(req: BillingCheckoutRequest): Promise<BillingCheckoutResult> {
  return apiPost<BillingCheckoutResult>('/billing/checkout', req)
}

/** GET /billing/orders —— 订单列表 */
export function getOrders(): Promise<BillingOrdersResult> {
  return apiGet<BillingOrdersResult>('/billing/orders')
}

/** POST /billing/portal —— Stripe 客户门户（管理订阅/换卡/退订） */
export function openPortal(): Promise<BillingPortalResult> {
  return apiPost<BillingPortalResult>('/billing/portal')
}

/** 整页跳转 Stripe（checkout url / 门户 url）。收口在模块层：
 *  react-hooks v7 的 immutability 规则禁止组件内直接改 window.location.href。 */
export function redirectToUrl(url: string): void {
  window.location.href = url
}
