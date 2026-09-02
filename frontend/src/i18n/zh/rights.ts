import { rightsEn } from '../en/rights'

/** rights 命名空间：中文与原文一致 */
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
    '证书按契约 §8.4 实时签发：每次查看都会生成一条新的签发记录与留痕事件，并固化当前版本的 SHA-256 指纹；本次会话内同一版本不会重复签发。',
  'rights.cert.errorNotAdopted': '该版本尚未采用候选，暂无法签发证书',
  'rights.cert.errorHint': '在作品详情页对候选点「采用定稿」后，即可签发授权证书。',
  'rights.cert.view': '查看证书',
  'rights.cert.download': '下载证书 JSON',
  'rights.cert.downloadStarted': '授权证书 JSON 已开始下载',
  'rights.cert.copyLink': '复制验证链接',
  'rights.cert.linkCopied': '已复制留痕验证链接',
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
  // 发行合规检查
  'rights.check.title': '发行合规检查',
  'rights.check.disclosure': 'AI 参与声明已写入 metadata（流媒体披露就绪）',
  'rights.check.watermarkFree':
    '免费档导出嵌入水印（当前以 SHA-256 指纹登记实现）· 升级付费档导出无水印',
  'rights.check.watermarkPaid': '不可听水印导出时嵌入 —— 本地引擎当前以 SHA-256 指纹登记实现，可溯源',
  'rights.check.loudness': '响度 −14 LUFS · 真峰值 −1.0 dBTP —— 导出目标规格（流媒体预设），非逐条实测',
  'rights.check.safety': '敏感词生成时校验 · 未检测到名人仿声 / 受保护采样',
  // 全局设置
  'rights.settings': '全局设置',
  'rights.setting.disclosure': '导出嵌入 AI 披露',
  'rights.setting.disclosureDesc': '自动在 metadata 声明 AI 参与度',
  'rights.setting.watermark': '不可听水印',
  'rights.setting.watermarkDesc': '导出时登记 SHA-256 内容指纹，可溯源（频域水印 V1.1）',
  'rights.setting.voiceVerify': '人声克隆双重验证',
  'rights.setting.voiceVerifyDesc': '仅本人 · 随机短语活体朗读',
  'rights.settingsNote':
    '证书由系统按契约 §8.4 签发：AI 披露、人类参与留痕与 SHA-256 指纹随作品版本固化。PDF 版证书将在 V1.1 提供。',
}
