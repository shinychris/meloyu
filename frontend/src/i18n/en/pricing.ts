/** pricing 命名空间：定价与积分（PricingView） */
export const pricingEn = {
  // 页头
  'pricing.label': 'Pricing / Plans & Credits',
  'pricing.title': 'Pay for your craft, not your anxiety',
  'pricing.monthly': 'Monthly',
  'pricing.yearly': 'Yearly',
  'pricing.save20': 'Save 20%',
  // 加载态
  'pricing.loading': 'Loading plans…',
  'pricing.loadFailed': 'Failed to load plans',
  // 套餐卡
  'pricing.popular': 'Most popular',
  'pricing.customPrice': 'Custom',
  'pricing.perMonth': ' $/mo',
  'pricing.tag.free': 'Jump in for free',
  'pricing.tag.proYearly': 'Billed yearly · credits roll over',
  'pricing.tag.yearlyOnly': 'Billed yearly',
  'pricing.tag.yearlyBetter': 'Yearly at ${price}/mo saves more',
  'pricing.tag.team': 'Seats · API · Batch',
  'pricing.monthlyCredits.pre': '· Monthly',
  'pricing.monthlyCredits.post': 'credits',
  // 切换按钮
  'pricing.current': 'Current plan',
  'pricing.switching': 'Switching…',
  'pricing.contactSales': 'Contact sales',
  'pricing.contactSalesToast': 'Team plan — please contact sales for a tailored quote',
  'pricing.downgrade': 'Downgrade to Free',
  'pricing.upgrade': 'Upgrade to {name}',
  'pricing.switched': 'Switched to "{name}" — this month’s credits have been granted',
  // 底部说明
  'pricing.footnote':
    'Commercial licensing is active while your subscription is valid; works generated and exported during the subscription keep their commercial rights. Credits are granted monthly and unused credits roll over. Current balance:',
  'pricing.creditsUnit': 'credits.',
  // 积分流水
  'pricing.tx.title': 'Credit transactions',
  'pricing.tx.time': 'Time',
  'pricing.tx.change': 'Change',
  'pricing.tx.reason': 'Reason',
  'pricing.tx.balance': 'Balance',
  'pricing.tx.task': 'Related task',
  'pricing.tx.empty': 'No transactions yet',
  // ===== Open API keys (FR-19, v0.8.2) =====
  'apikey.title': 'Open API (beta)',
  'apikey.hint': "Four machine endpoints — text-to-song / task polling / works listing / file download — authenticated by API key. Usage is billed to this account's credits at the same rates as in-app (v1_pro=12 / v1_fast=6); commercial licensing follows the account plan × channel license (same certificate).",
  'apikey.namePlaceholder': 'Key name (e.g. production)',
  'apikey.issue': 'Issue key',
  'apikey.revoke': 'Revoke',
  'apikey.empty': 'No keys yet',
  'apikey.freshNotice': 'The full key is shown only once — copy it now (lost keys can only be revoked and reissued)',
  'apikey.toast.nameRequired': 'Enter a key name first',
  'apikey.endpointHint': 'Usage: POST /api/v1/public/generations (X-API-Key header) → poll GET /api/v1/public/tasks/{id} → download via the downloads links once succeeded. Rate limit: 30 generations/hour (shared with in-app quota).',
} as const
