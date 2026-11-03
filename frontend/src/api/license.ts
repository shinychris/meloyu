import { apiGet, apiPost } from './client'
import type { LicenseActivateResult, LicenseStatus } from '../types/api'

/**
 * v0.16.0 License（买断制）：
 * - status：试用/激活状态（cloud 模式亦可调用，返回 mode=cloud 供前端分支）；
 * - activate：输入 License Key（Ed25519 离线验签），激活即全功能；
 * - deactivate：解除激活（试用到期后由闸门接管，40203 引导至此页）。
 */

/** GET /licenses/status —— 试用与激活状态 */
export function getLicenseStatus(): Promise<LicenseStatus> {
  return apiGet<LicenseStatus>('/licenses/status')
}

/** POST /licenses/activate-online —— 在线激活（账户+激活码，portal 兑换签名密钥） */
export function activateLicenseOnline(account: string, code: string): Promise<LicenseActivateResult> {
  return apiPost<LicenseActivateResult>('/licenses/activate-online', { account, code })
}

/** POST /licenses/activate —— 离线激活（粘贴完整授权密钥，Ed25519 本地验签） */
export function activateLicense(license_key: string): Promise<LicenseActivateResult> {
  return apiPost<LicenseActivateResult>('/licenses/activate', { license_key })
}

/** POST /licenses/deactivate —— 解除激活 */
export function deactivateLicense(): Promise<LicenseStatus> {
  return apiPost<LicenseStatus>('/licenses/deactivate')
}
