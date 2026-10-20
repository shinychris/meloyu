/**
 * settings 命名空间（v0.17.0）：系统设置页——通用（语言/数据目录/导出）、
 * 用量统计与分析（用户自定义 API 口径）、授权与激活（自定价页迁入）、
 * 引擎与 API 快捷入口。license（桌面买断）模式专属页，cloud 模式回定价页。
 */
export const settingsEn = {
  // 页头
  'settings.label': 'Settings / System',
  'settings.title': 'System settings',
  'settings.loading': 'Loading…',
  // 分区导航
  'settings.nav.general': 'General',
  'settings.nav.usage': 'Usage & analytics',
  'settings.nav.license': 'License',
  'settings.nav.engines': 'Engines & API',
  // ===== 通用 =====
  'settings.general.language': 'Language',
  'settings.general.appInfo': 'About',
  'settings.general.edition': 'Edition',
  'settings.general.edition.desktop': 'Desktop (one-time license)',
  'settings.general.edition.cloud': 'Cloud (legacy)',
  'settings.general.edition.enterprise': 'Enterprise (private deployment)',
  'settings.general.version': 'Version',
  'settings.general.dataDir': 'Data directory',
  'settings.general.dataDirNote':
    'Where works, models and settings live on this machine.',
  'settings.general.data': 'Data',
  // ===== 用量统计与分析 =====
  'settings.usage.desc':
    'No official credits are consumed — this app is a one-time purchase. ' +
    'Usage below is statistics only: cloud API channels bill your own API keys, ' +
    'local engines use this machine.',
  'settings.usage.window': 'Last {n} days',
  'settings.usage.allTime': 'All time',
  'settings.usage.card.calls': 'Generations',
  'settings.usage.card.units': 'Usage units',
  'settings.usage.card.successRate': 'Success rate',
  'settings.usage.card.remoteCalls': 'Cloud API calls',
  'settings.usage.byDay': 'Daily trend (units)',
  'settings.usage.byEngine': 'By engine channel',
  'settings.usage.engine': 'Engine',
  'settings.usage.kind': 'Type',
  'settings.usage.kind.remote': 'Cloud API · your key',
  'settings.usage.kind.local': 'Local',
  'settings.usage.succeeded': 'Succeeded',
  'settings.usage.lyricsTitle': 'Lyrics engine calls',
  'settings.usage.empty': 'No usage in this window yet',
  'settings.usage.emptyEngine': 'No engine usage yet',
  // ===== 引擎与 API 入口 =====
  'settings.engines.desc':
    'Engine channels, API keys and local models are configured in the model center.',
  'settings.engines.open': 'Open model center',
}
