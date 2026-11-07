import { pricingEn } from '../en/pricing'

/** pricing 命名空间：中文与原文一致（2026-11-06 起开源免费口径，计费功能保留） */
export const pricingZh: Record<keyof typeof pricingEn, string> = {
  // 页头
  'pricing.label': 'Pricing / 定价与积分',
  'pricing.title': '免费 · 开源（MIT）',
  // 加载态
  'pricing.loading': '加载中…',
  'pricing.loadFailed': '加载失败',
  // 授权卡（LICENSE_SKU 单档，与落地页同源；开源免费口径）
  'pricing.buy.badge': '开源免费',
  'pricing.buy.oneTime': '一次性买断 · 终身',
  'pricing.buy.freePrice': '免费 · 开源（MIT）',
  'pricing.buy.cta': '前往官网获取',
  'pricing.buy.note': 'Meloyu 现已开源（MIT）并免费提供；既有终身授权继续有效。',
  'pricing.buy.enterprise': '需要私有化部署或团队批量授权？请联系销售。',
  // 用量说明（license 模式积分=纯计量）
  'pricing.usage.footnote':
    '用量记录——生成/编辑成本仅作计量参考，桌面版中不扣减、不会用尽。',
  'pricing.usage.title': '用量记录',
  // cloud 存量：订阅停售公告
  'pricing.sunsetTitle': '订阅已停售',
  'pricing.sunsetDesc':
    'Meloyu 现已开源（MIT）并免费提供——不再有月费，也无需购买授权。存量档位在过渡期内继续有效（下方只读参考），新订阅不再受理。',
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
  // ===== 开放 API 密钥（v0.8.2）=====
  'apikey.title': '开放 API（β）',
  'apikey.hint': '文本生歌 / 任务查询 / 作品列表 / 文件下载四个机器接口，密钥鉴权；用量按本账号计量（与站内同价：v1_pro=12 / v1_fast=6），商用授权随账号档位×通道许可（证书同源）。',
  'apikey.namePlaceholder': '密钥名（如 production）',
  'apikey.issue': '签发密钥',
  'apikey.revoke': '吊销',
  'apikey.empty': '还没有密钥',
  'apikey.freshNotice': '完整密钥仅此一次显示，请立即复制保存（丢失只能吊销重发）',
  'apikey.toast.nameRequired': '请先填写密钥名',
  'apikey.confirm.revokeTitle': '吊销 API 密钥「{name}」？',
  'apikey.confirm.revokeDesc': '使用该密钥的集成立即失效，操作不可撤销。',
  'apikey.endpointHint': '调用方式：POST /api/v1/public/generations（X-API-Key 头）→ 轮询 GET /api/v1/public/tasks/{id} → succeeded 后按 downloads 链接下载。限流：生歌 30 次/小时（与站内共享额度）。',
}
