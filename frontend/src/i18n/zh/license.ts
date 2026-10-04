import { licenseEn } from '../en/license'

/** license 命名空间：zh 与 en key 严格一一对应（编译期校验，漏 key 报 type error） */
export const licenseZh: Record<keyof typeof licenseEn, string> = {
  // 侧栏徽标（替换积分余额条，license 模式）
  'license.sidebar.label': '授权',
  'license.sidebar.trial': '试用',
  'license.sidebar.daysUnit': ' 天剩余',
  'license.sidebar.lifetime': '终身',
  'license.sidebar.expired': '已到期',
  // 账号菜单档位行（license 模式）
  'license.menu.planLabel': '本地档案',
  // 在线激活（2026-10-04 口径：邮件交付账户+激活码，在线兑换）
  'license.online.title': '使用激活码激活',
  'license.online.desc':
    '购买邮件中包含你的账户与激活码（MELOYU-XXXX-XXXX 格式），在下方输入即可。激活仅需一次，之后完全离线可用。',
  'license.online.accountLabel': '账户（购买邮箱）',
  'license.online.accountPlaceholder': 'you@example.com',
  'license.online.codeLabel': '激活码',
  'license.online.codePlaceholder': 'MELOYU-XXXXXXXX-XXXXXXXX',
  'license.online.cta': '在线激活',
  'license.online.doing': '激活中…',
  'license.online.done': '激活成功——终身使用',
  'license.offline.fold': '离线激活？使用完整授权密钥',
  // 激活卡片
  'license.activate.label': '激活',
  'license.activate.title': '激活终身授权',
  'license.activate.desc':
    '粘贴购买邮件（或 meloyu.com）中的 License Key 即可。激活为本地离线验签——无需账号、无需联网。',
  'license.activate.placeholder': 'MELOYU 授权密钥（v1.…）',
  'license.activate.cta': '激活',
  'license.activate.activating': '激活中…',
  'license.activate.done': '激活成功——终身使用',
  'license.activate.deactivate': '在此设备解除授权',
  'license.activate.deactivating': '解除中…',
  'license.activate.deactivated': '已在此设备解除授权',
  // 状态卡（试用）
  'license.trial.title': '免费试用',
  'license.trial.desc': '试用期内全部功能开放——无注册、无积分。',
  'license.trial.daysLeft': '剩余 {n} 天',
  'license.trial.expiresAt': '{date} 到期',
  'license.trial.expiredTitle': '试用已结束',
  'license.trial.expiredDesc':
    '生成、编辑与导出已锁定。在下方激活终身授权即可继续创作；已有作品的浏览与播放不受影响。',
  // 状态卡（已激活）
  'license.status.title': '终身授权',
  'license.status.active': '已生效',
  'license.status.tier.lifetime': '个人版 · 终身',
  'license.status.tier.enterprise': '企业版',
  'license.status.licenseId': '授权编号',
  'license.status.activatedAt': '激活时间',
  'license.status.note': '授权对象',
}
