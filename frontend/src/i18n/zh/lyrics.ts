import { lyricsEn } from '../en/lyrics'

/** zh 字典 key 与 en 严格一一对应（编译期校验，漏 key 报 type error）；zh 保持原文案 */
export const lyricsZh: Record<keyof typeof lyricsEn, string> = {
  // ===== 视图头部 =====
  'lyrics.header.label': 'Lyrics / 歌词助手',
  'lyrics.header.headline': '写词，并与旋律对齐',
  'lyrics.engine.badge': '引擎：{engine} ⇄',
  'lyrics.engine.title': '在模型中心切换 AI 引擎（本地规则 / 本地开源模型 / 外部 API）',
  // ===== 生成参数 =====
  'lyrics.theme.label': '主题 / 一句话（生成用，必填）',
  'lyrics.theme.placeholder': '例：雨夜便利店等待',
  'lyrics.mood.label': '情绪（可选，如：忧郁 / 热血）',
  'lyrics.mood.placeholder': '命中意象库',
  // ===== 操作按钮 =====
  'lyrics.action.generate': 'AI 生成歌词',
  'lyrics.action.generating': '生成中…',
  'lyrics.action.generatingLLM': 'AI 生成中（最长约 3 分钟）…',
  'lyrics.action.generateTitle': 'LLM 引擎生成中，视模型 10s~3min',
  'lyrics.action.polish': '润色选中段',
  'lyrics.action.polishing': '润色中…',
  'lyrics.action.rhyme': '押韵 / 重音检查',
  'lyrics.action.checking': '检查中…',
  'lyrics.action.tags': '补全结构标签',
  'lyrics.action.bridge': '续写桥段',
  'lyrics.action.bridgeSoon': '续写桥段将在 V1.1 上线',
  'lyrics.action.apply': '应用到工作台 →',
  // ===== 备选版本 =====
  'lyrics.alternatives': '备选版本',
  'lyrics.alternative': '备选 {n}',
  'lyrics.toast.altLoaded': '已载入备选 {n}',
  // ===== 提示 =====
  'lyrics.toast.themeRequired': '先填一个主题或一句话（1~100 字）',
  'lyrics.toast.empty': '歌词为空',
  'lyrics.toast.fallback': '引擎不可用已回退本地规则：{reason}',
  'lyrics.toast.generated': 'AI 已生成歌词草稿（{engine}），可继续润色',
  'lyrics.toast.polishedSection': '已润色{section}（{n} 处修改）',
  'lyrics.toast.polishedAll': '已润色全文（{n} 处修改）',
  'lyrics.toast.rhymeOff': '检查完成：{n} 处出韵，主韵 {group}',
  'lyrics.toast.rhymeAll': '检查完成：全部押韵（主韵 {group}）',
  'lyrics.toast.tagsInferred': '原歌词无标签，已按模板补全结构',
  'lyrics.toast.tagsNormalized': '已识别并规范化结构标签',
  'lyrics.toast.applied': '已应用到创作工作台的歌词框',
  'lyrics.toast.backStudio': '已回到创作工作台',
  // ===== 操作日志（VersionTree 展示） =====
  'lyrics.log.generated': '歌词助手：AI 生成草稿',
  // ===== 右侧分析面板 =====
  'lyrics.panel.structure': '结构建议',
  'lyrics.panel.structureDefault': '副歌核心句建议重复 2–3 次；桥段可降半音营造对比，末副歌回升。',
  'lyrics.panel.sectionCount': '{section} {n} 行',
  'lyrics.panel.tagDetect': '标签检测：{tags}',
  'lyrics.panel.none': '无',
  'lyrics.panel.polishLog': '润色记录',
  'lyrics.panel.stress': '重音对齐',
  'lyrics.panel.stressOk': '重音落拍正常',
  'lyrics.panel.stressPending': '运行「押韵 / 重音检查」后显示',
  'lyrics.panel.rhyme': '韵脚',
  'lyrics.panel.rhymeMain': ' · 主韵 {group}',
  'lyrics.panel.backStudio': '返回工作台 →',
  'lyrics.defaultLyrics':
    '[Verse]\n雨停在凌晨三点的窗台\n霓虹把影子拉得好白\n便利店的灯还亮着\n像没说完的对白\n\n[Pre-Chorus]\n我数着屋檐滴落的节拍\n一下一下都是等待\n\n[Chorus]\n我们把未来说得太轻\n像风穿过无人的街心\n承诺若只剩回音\n至少今夜还有雨声',
}
