/**
 * billing 命名空间：v0.7.0 计费（PricingView 支付流 / 充值包 / 管理订阅 /
 * BillingReturnView 支付回跳页）。
 */
export const billingEn = {
  // PricingView · 充值积分包卡
  'billing.topup.label': 'Top-up',
  'billing.topup.title': 'Credit top-up pack',
  'billing.topup.desc':
    'One-time purchase — credits never expire and stack on top of your monthly grant. Handy when a deadline needs a few more runs.',
  'billing.topup.cta': 'Buy 1,000 credits',
  'billing.topup.buying': 'Redirecting…',
  // PricingView · 管理订阅
  'billing.manage': 'Manage subscription',
  'billing.manageTitle': 'Manage payment method / invoices / cancellation in the Stripe customer portal',
  'billing.manageOpening': 'Opening portal…',
  // 订阅按钮跳转中
  'billing.checkout.redirecting': 'Redirecting to checkout…',
  // BillingReturnView（#/billing/return?status=success|cancel）
  'billing.return.label': 'Billing',
  'billing.return.successTitle': 'Payment received',
  'billing.return.successDesc':
    'Your payment is being processed. The subscription or top-up is activated asynchronously by the payment webhook — usually within a few seconds.',
  'billing.return.refreshHint':
    'Plan not updated yet? Wait a few seconds, then refresh your status below.',
  'billing.return.refresh': 'Refresh status',
  'billing.return.refreshing': 'Refreshing…',
  'billing.return.refreshed': 'Status refreshed',
  'billing.return.backPricing': 'Back to pricing',
  'billing.return.backStudio': 'Back to studio',
  'billing.return.cancelTitle': 'Checkout canceled',
  'billing.return.cancelDesc': 'You were not charged. You can pick a plan again at any time.',
} as const
