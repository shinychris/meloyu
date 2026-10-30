import { rightsEn } from '../en/rights'

/** rights 命名空间：zh 与 en key 严格一一对应（编译期校验，漏 key 报 type error）。
 *  v0.7.0「去虚还实」：checklist 只陈述真实能力，摆设开关整段下架。 */
export const rightsZh: Record<keyof typeof rightsEn, string> = {
  // 页头
  'rights.label': 'Rights / 合规与权利中心',
  'rights.title': '每一首，都有清白凭证',
  // 授权证书卡
  'rights.cert.cardTitle': '授权证书',
  'rights.cert.noWorks': '暂无作品',
  'rights.cert.loading': '读取证书…',
  'rights.cert.viewHint': '点击查看并签发授权证书',
  'rights.cert.realtimeNote':
    '证书实时签发：每次查看都会生成一条新的签发记录与留痕事件，并固化当前版本的 SHA-256 指纹；本次会话内同一版本不会重复签发。',
  'rights.cert.errorNotAdopted': '该版本尚未采用候选，暂无法签发证书',
  'rights.cert.errorHint': '在作品详情页对候选点「采用定稿」后，即可签发授权证书。',
  'rights.cert.view': '查看证书',
  'rights.cert.download': '下载证书 JSON',
  'rights.cert.downloadStarted': '授权证书 JSON 已开始下载',
  'rights.cert.copyApiRef': '复制取证引用（API）',
  'rights.cert.apiRefCopied': '已复制取证引用（API 地址），可用于调取证书 JSON 核验',
  'rights.cert.errorNoVersion': '该作品还没有已采用的定稿版本，暂无证书可签发',
  'rights.cert.copyFailed': '复制失败，请手动复制：{link}',
  // 证书字段
  'rights.field.workId': '作品 ID',
  'rights.field.modelVersion': '模型 / 版本',
  'rights.field.generatedAt': '生成时间',
  'rights.field.licenseType': '许可类型',
  'rights.field.humanTrail': '人类创作留痕',
  'rights.field.fingerprint': '内容指纹',
  'rights.license.commercial': '商用授权',
  'rights.license.nonCommercial': '非商用',
  'rights.trail.count': '共 {n} 条',
  // 空状态
  'rights.empty': '暂无在库作品，去创作工作台生成第一首歌后再来签发证书。',
  // 发行合规检查（v0.7.0：真实数据驱动，只陈述实际存在的能力）
  'rights.check.title': '发行合规检查',
  'rights.check.disclosure': 'AI 生成披露已写入每份授权证书',
  'rights.check.fingerprint': '作品母带/预览 SHA-256 指纹登记',
  'rights.check.loudness': '−14 LUFS 为导出目标规格，非逐项实测',
  'rights.check.safety': '内置基础敏感词过滤（可扩展运营词库）',
  // 授权说明（替代原三个摆设开关；商用权利跟随通道模型许可）
  'rights.licenseNotes.title': '授权说明',
  'rights.licenseNotes.intro': '商用权利跟随生成通道的模型许可：',
  'rights.licenseNotes.commercial': '可商用通道：本地合成引擎 · ACE-Step（MIT）· Apache-2.0 系模型',
  'rights.licenseNotes.nonCommercial': '非商用：MusicGen（CC-BY-NC 权重）· SongGeneration（腾讯学术许可）',
  'rights.licenseNotes.conditional': '有条件商用：MiniMax / Stable Audio —— 需满足其社区许可的收入门槛',
  'rights.settingsNote':
    '证书由系统签发：AI 披露、人类参与留痕与 SHA-256 指纹随作品版本固化。PDF 版证书将在 V1.1 提供。',
}
