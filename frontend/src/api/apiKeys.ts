/**
 * 开放 API 密钥 API。
 * ：从 ApiKeysCard 组件内联请求收敛到 api/ 分层。
 */
import { apiDelete, apiGet, apiPost } from './client'
import type { ApiKeyInfo } from '../types/api'

/** GET /api-keys —— 密钥列表（完整 key 仅签发时返回一次） */
export function listApiKeys(): Promise<{ items: ApiKeyInfo[]; total: number }> {
  return apiGet('/api-keys')
}

/** POST /api-keys —— 签发密钥（响应含完整 key，仅此一次） */
export function createApiKey(name: string): Promise<ApiKeyInfo & { key: string }> {
  return apiPost('/api-keys', { name })
}

/** DELETE /api-keys/{id} —— 吊销密钥 */
export function revokeApiKey(keyId: string): Promise<{ ok: boolean }> {
  return apiDelete(`/api-keys/${keyId}`)
}
