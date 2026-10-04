/**
 * 落地页站点模式（F7，2026-10-03 定位转型）：
 * 同一套 Landing 组件服务两种宿主——
 * - App 内（site=false）：登录/进工作台的 CTAs 走 react-router（现状）；
 * - 官网营销站（site=true，portal 托管的独立构建）：无 App 会话语境——
 *   隐藏登录类入口、购买 CTA 直链 /buy（portal → Stripe Payment Link）。
 */
import { createContext, useContext } from 'react'

const SiteModeContext = createContext<boolean>(false)

export const SiteModeProvider = SiteModeContext.Provider

export function useSiteMode(): boolean {
  return useContext(SiteModeContext)
}
