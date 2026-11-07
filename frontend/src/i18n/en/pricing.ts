/** pricing 命名空间：定价与积分（v0.17.0 起 cloud 存量专用；激活/授权卡已迁入 settings 命名空间的系统设置页；
 *  2026-11-06 起对外口径为开源免费（MIT），计费功能保留） */
export const pricingEn = {
  // 页头
  'pricing.label': 'Pricing / Plans & Credits',
  'pricing.title': 'Free & open source (MIT)',
  // 加载态
  'pricing.loading': 'Loading…',
  'pricing.loadFailed': 'Failed to load',
  // 授权卡（LICENSE_SKU 单档，与落地页同源；开源免费口径）
  'pricing.buy.badge': 'Open source',
  'pricing.buy.oneTime': 'one-time · lifetime',
  'pricing.buy.freePrice': 'Free · open source (MIT)',
  'pricing.buy.cta': 'Get it at meloyu.com',
  'pricing.buy.note':
    'Meloyu is now free and open source (MIT). Existing lifetime licenses remain valid and honored.',
  'pricing.buy.enterprise': 'Need on-premise deployment or team licensing? Contact sales.',
  // 用量说明（license 模式积分=纯计量）
  'pricing.usage.footnote':
    'Usage log — generation/editing costs are metered for your reference only; nothing is deducted and nothing runs out in the desktop app.',
  'pricing.usage.title': 'Usage log',
  // cloud 存量：订阅停售公告
  'pricing.sunsetTitle': 'Subscriptions have been retired',
  'pricing.sunsetDesc':
    'Meloyu is now free and open source (MIT) — no monthly fees and no license purchase. Your current plan stays active for the transition period (read-only reference below); new subscriptions are no longer sold.',
  'pricing.plansRefTitle': 'Plan quotas (reference)',
  'pricing.planRef': 'Current plan',
  'pricing.monthlyCredits.pre': '· Monthly',
  'pricing.monthlyCredits.post': 'credits',
  // 流水/用量表
  'pricing.tx.title': 'Credit transactions',
  'pricing.tx.time': 'Time',
  'pricing.tx.change': 'Change',
  'pricing.tx.reason': 'Reason',
  'pricing.tx.balance': 'Balance',
  'pricing.tx.task': 'Related task',
  'pricing.tx.empty': 'No records yet',
  // ===== Open API keys (, v0.8.2) =====
  'apikey.title': 'Open API (beta)',
  'apikey.hint': "Four machine endpoints — text-to-song / task polling / works listing / file download — authenticated by API key. Usage is metered to this account at the same rates as in-app (v1_pro=12 / v1_fast=6); commercial licensing follows the account plan × channel license (same certificate).",
  'apikey.namePlaceholder': 'Key name (e.g. production)',
  'apikey.issue': 'Issue key',
  'apikey.revoke': 'Revoke',
  'apikey.empty': 'No keys yet',
  'apikey.freshNotice': 'The full key is shown only once — copy it now (lost keys can only be revoked and reissued)',
  'apikey.toast.nameRequired': 'Enter a key name first',
  'apikey.confirm.revokeTitle': 'Revoke API key "{name}"?',
  'apikey.confirm.revokeDesc': 'Integrations using this key stop working immediately. This cannot be undone.',
  'apikey.endpointHint': 'Usage: POST /api/v1/public/generations (X-API-Key header) → poll GET /api/v1/public/tasks/{id} → download via the downloads links once succeeded. Rate limit: 30 generations/hour (shared with in-app quota).',
} as const
