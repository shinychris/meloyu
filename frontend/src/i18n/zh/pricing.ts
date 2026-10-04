import { pricingEn } from '../en/pricing'

/** pricing 命名空间：中文与原文一致（v0.16.0 买断制口径） */
export const pricingZh: Record<keyof typeof pricingEn, string> = {
  // 页头
  'pricing.label': 'Pricing / 定价与激活',
  'pricing.title': '一次买断，终身使用',
  // 加载态
  'pricing.loading': '加载中…',
  'pricing.loadFailed': '加载失败',
  // 买断卡（LICENSE_SKU 单档，与落地页同源）
  'pricing.buy.badge': '限时首发',
  'pricing.buy.oneTime': '一次性买断 · 终身',
  'pricing.buy.cta': '前往官网购买',
  'pricing.buy.note': '一次付清买断。含全部版本更新；无订阅、无积分。',
  'pricing.buy.enterprise': '需要私有化部署或团队批量授权？请联系销售。',
  // 用量说明（license 模式积分=纯计量）
  'pricing.usage.footnote':
    '用量记录——生成/编辑成本仅作计量参考，桌面版中不扣减、不会用尽。',
  'pricing.usage.title': '用量记录',
  // cloud 存量：订阅停售公告
  'pricing.sunsetTitle': '订阅已停售',
  'pricing.sunsetDesc':
    'Meloyu 已转型为桌面软件，终身授权一次买断（$399，限时首发 $159）——不再有月费。存量档位在过渡期内继续有效，新订阅不再受理。',
  'pricing.plansRefTitle': '档位配额（参考）',
  'pricing.planRef': '当前档位',
  'pricing.monthlyCredits.pre': '· 每月',
  'pricing.monthlyCredits.post': '积分',
  // 流水/用量表
  'pricing.tx.title': '积分流水',
  'pricing.tx.time': '时间',
  'pricing.tx.change': '变动',
  'pricing.tx.reason': '原因',
  'pricing.tx.balance': '余额',
  'pricing.tx.task': '关联任务',
  'pricing.tx.empty': '暂无记录',
  // ===== 开放 API 密钥（FR-19，v0.8.2）=====
  'apikey.title': '开放 API（β）',
  'apikey.hint': '文本生歌 / 任务查询 / 作品列表 / 文件下载四个机器接口，密钥鉴权；用量按本账号计量（与站内同价：v1_pro=12 / v1_fast=6），商用授权随账号档位×通道许可（证书同源）。',
  'apikey.namePlaceholder': '密钥名（如 production）',
  'apikey.issue': '签发密钥',
  'apikey.revoke': '吊销',
  'apikey.empty': '还没有密钥',
  'apikey.freshNotice': '完整密钥仅此一次显示，请立即复制保存（丢失只能吊销重发）',
  'apikey.toast.nameRequired': '请先填写密钥名',
  'apikey.endpointHint': '调用方式：POST /api/v1/public/generations（X-API-Key 头）→ 轮询 GET /api/v1/public/tasks/{id} → succeeded 后按 downloads 链接下载。限流：生歌 30 次/小时（与站内共享额度）。',
}
