import { apiGet, apiPost } from './client'
import type {
  CreditsBalance,
  CreditTransaction,
  Paginated,
  PlansResult,
  SystemMeta,
  User,
} from '../types/api'

/** GET /credits/balance —— 积分余额 */
export function getCreditsBalance(): Promise<CreditsBalance> {
  return apiGet<CreditsBalance>('/credits/balance')
}

/** GET /credits/transactions —— 积分流水（分页） */
export function getCreditTransactions(params?: {
  page?: number
  page_size?: number
}): Promise<Paginated<CreditTransaction>> {
  return apiGet<Paginated<CreditTransaction>>('/credits/transactions', params)
}

/** GET /subscriptions/plans —— 订阅档位 */
export function getPlans(): Promise<PlansResult> {
  return apiGet<PlansResult>('/subscriptions/plans')
}

/** POST /subscriptions/switch —— 切换档位（MVP 无支付；team 不可切换） */
export function switchPlan(plan: 'free' | 'pro' | 'studio'): Promise<User> {
  return apiPost<User>('/subscriptions/switch', { plan })
}

/** GET /system/meta —— 枚举元数据（无鉴权）：下拉框与灵感 chips 数据源 */
export function getSystemMeta(): Promise<SystemMeta> {
  return apiGet<SystemMeta>('/system/meta')
}
