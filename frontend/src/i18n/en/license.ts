/**
 * license 命名空间（v0.16.0 定位转型）：买断制激活 / 试用状态 / 侧栏徽标。
 * 原 billing（Stripe）命名空间已随订阅拆除移除。
 */
export const licenseEn = {
  // 侧栏徽标（替换积分余额条，license 模式）
  'license.sidebar.label': 'License',
  'license.sidebar.trial': 'Trial',
  'license.sidebar.daysUnit': 'd left',
  'license.sidebar.lifetime': 'Lifetime',
  'license.sidebar.expired': 'Expired',
  // 账号菜单档位行（license 模式）
  'license.menu.planLabel': 'Local profile',
  // 激活卡片
  'license.activate.label': 'Activate',
  'license.activate.title': 'Activate your lifetime license',
  'license.activate.desc':
    'Paste the license key from your purchase email (or from meloyu.com). Activation is verified offline — no account or internet required.',
  'license.activate.placeholder': 'MELOYU license key (v1.…)',
  'license.activate.cta': 'Activate',
  'license.activate.activating': 'Activating…',
  'license.activate.done': 'License activated — enjoy Meloyu for life',
  'license.activate.deactivate': 'Deactivate on this device',
  'license.activate.deactivating': 'Deactivating…',
  'license.activate.deactivated': 'License removed from this device',
  // 状态卡（试用）
  'license.trial.title': 'Free trial',
  'license.trial.desc': 'Full features during the trial — no signup, no credits.',
  'license.trial.daysLeft': '{n} days left',
  'license.trial.expiresAt': 'Ends {date}',
  'license.trial.expiredTitle': 'Trial ended',
  'license.trial.expiredDesc':
    'Generating, editing and exporting are locked. Activate a lifetime license below to continue — browsing and playing existing works stays free.',
  // 状态卡（已激活）
  'license.status.title': 'Lifetime license',
  'license.status.active': 'Active',
  'license.status.tier.lifetime': 'Personal · Lifetime',
  'license.status.tier.enterprise': 'Enterprise',
  'license.status.licenseId': 'License ID',
  'license.status.activatedAt': 'Activated at',
  'license.status.note': 'Licensed to',
} as const
