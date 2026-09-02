import { billingEn } from '../en/billing'

/** billing 命名空间：zh 与 en key 严格一一对应（编译期校验，漏 key 报 type error） */
export const billingZh: Record<keyof typeof billingEn, string> = {
  // PricingView · 充值积分包卡
  'billing.topup.label': '充值',
  'billing.topup.title': '充值积分包',
  'billing.topup.desc':
    '一次性购买 —— 积分永不过期，叠加在每月发放之上。赶稿需要多跑几轮时最合适。',
  'billing.topup.cta': '购买 1,000 积分',
  'billing.topup.buying': '跳转中…',
  // PricingView · 管理订阅
  'billing.manage': '管理订阅',
  'billing.manageTitle': '在 Stripe 客户门户管理支付方式 / 账单 / 退订',
  'billing.manageOpening': '正在打开门户…',
  // 订阅按钮跳转中
  'billing.checkout.redirecting': '正在跳转收银台…',
  // BillingReturnView（#/billing/return?status=success|cancel）
  'billing.return.label': '计费',
  'billing.return.successTitle': '已收到付款',
  'billing.return.successDesc':
    '支付正在处理中。订阅或充值积分由支付 webhook 异步激活 —— 通常几秒内到账。',
  'billing.return.refreshHint': '档位还没变？等几秒后点下面的按钮刷新状态。',
  'billing.return.refresh': '刷新状态',
  'billing.return.refreshing': '刷新中…',
  'billing.return.refreshed': '状态已刷新',
  'billing.return.backPricing': '回到定价页',
  'billing.return.backStudio': '回到工作台',
  'billing.return.cancelTitle': '已取消支付',
  'billing.return.cancelDesc': '未产生任何扣款。你可以随时重新选择方案。',
}
