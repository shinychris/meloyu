import { pricingEn } from '../en/pricing'

/** pricing 命名空间：中文与原文一致 */
export const pricingZh: Record<keyof typeof pricingEn, string> = {
  // 页头
  'pricing.label': 'Pricing / 定价与积分',
  'pricing.title': '为创作付费，不为焦虑付费',
  'pricing.monthly': '按月',
  'pricing.yearly': '按年',
  'pricing.save20': '省 20%',
  // 加载态
  'pricing.loading': '加载档位…',
  'pricing.loadFailed': '档位信息加载失败',
  // 套餐卡
  'pricing.popular': '最受欢迎',
  'pricing.customPrice': '定制',
  'pricing.perMonth': ' ¥/月',
  'pricing.tag.free': '先玩起来',
  'pricing.tag.proYearly': '按年付 · 积分可结转',
  'pricing.tag.yearlyOnly': '按年付',
  'pricing.tag.yearlyBetter': '年付 ¥{price}/月 更划算',
  'pricing.tag.team': '席位 · API · 批量',
  'pricing.monthlyCredits.pre': '· 每月',
  'pricing.monthlyCredits.post': '积分',
  // 切换按钮
  'pricing.current': '当前方案',
  'pricing.switching': '切换中…',
  'pricing.contactSales': '联系销售',
  'pricing.contactSalesToast': '团队版请联系销售（MVP 演示）',
  'pricing.downgrade': '降级到免费',
  'pricing.upgrade': '升级 {name}',
  'pricing.switched': '已切换至「{name}」，积分已按月发放',
  // 底部说明
  'pricing.footnote':
    '商用授权随有效订阅生效；订阅期内生成并导出的作品保留商用权利。积分按月发放、未用完可结转。当前余额',
  'pricing.creditsUnit': '积分。',
  // 积分流水
  'pricing.tx.title': '积分流水',
  'pricing.tx.time': '时间',
  'pricing.tx.change': '变动',
  'pricing.tx.reason': '原因',
  'pricing.tx.balance': '余额',
  'pricing.tx.task': '关联任务',
  'pricing.tx.empty': '暂无流水记录',
}
