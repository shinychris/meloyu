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
  // 在线激活（2026-10-04 口径：邮件交付账户+激活码，在线兑换）
  'license.online.title': 'Activate with your code',
  'license.online.desc':
    'Your purchase email contains your account and an activation code (MELOYU-XXXX-XXXX). Enter both below — activation is one-time; the app works fully offline afterwards.',
  'license.online.accountLabel': 'Account (purchase email)',
  'license.online.accountPlaceholder': 'you@example.com',
  'license.online.codeLabel': 'Activation code',
  'license.online.codePlaceholder': 'MELOYU-XXXXXXXX-XXXXXXXX',
  'license.online.cta': 'Activate online',
  'license.online.doing': 'Activating…',
  'license.online.done': 'Activated — enjoy Meloyu for life',
  'license.offline.fold': 'Prefer offline activation? Use the full license key',
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
