import { settingsEn } from '../en/settings'

/** settings 命名空间：系统设置页（zh 全量覆盖；license 桌面买断模式专属页） */
export const settingsZh: Record<keyof typeof settingsEn, string> = {
  // 页头
  'settings.label': 'Settings / 系统设置',
  'settings.title': '系统设置',
  'settings.loading': '加载中…',
  // 分区导航
  'settings.nav.general': '通用',
  'settings.nav.usage': '用量统计',
  'settings.nav.license': '授权',
  'settings.nav.engines': '引擎与 API',
  // ===== 通用 =====
  'settings.general.language': '语言',
  'settings.general.appInfo': '应用信息',
  'settings.general.edition': '产品形态',
  'settings.general.edition.desktop': '桌面版（单次买断授权）',
  'settings.general.edition.cloud': '云版（存量）',
  'settings.general.edition.enterprise': '企业版（私有化部署）',
  'settings.general.version': '版本',
  'settings.general.dataDir': '数据目录',
  'settings.general.dataDirNote': '作品、模型与配置在本机的存放位置。',
  'settings.general.data': '数据',
  // ===== 用量统计与分析 =====
  'settings.usage.desc':
    '本软件为单次买断授权，不消耗任何官方积分——以下用量仅作统计与分析：' +
    '云端 API 通道的调用消耗你自己配置的 API Key，本地引擎仅使用本机算力。',
  'settings.usage.window': '近 {n} 天',
  'settings.usage.allTime': '累计',
  'settings.usage.card.calls': '生成次数',
  'settings.usage.card.units': '用量单位',
  'settings.usage.card.successRate': '成功率',
  'settings.usage.card.remoteCalls': '云端 API 调用',
  'settings.usage.byDay': '每日趋势（用量单位）',
  'settings.usage.byEngine': '按引擎通道',
  'settings.usage.engine': '引擎通道',
  'settings.usage.kind': '类型',
  'settings.usage.kind.remote': '云端 API · 自有 Key',
  'settings.usage.kind.local': '本地',
  'settings.usage.succeeded': '成功',
  'settings.usage.lyricsTitle': '歌词引擎调用',
  'settings.usage.empty': '窗口内暂无用量',
  'settings.usage.emptyEngine': '暂无引擎用量',
  // ===== 引擎与 API 入口 =====
  'settings.engines.desc': '引擎通道、API Key 与本地模型在模型中心配置。',
  'settings.engines.open': '打开模型中心',
}
