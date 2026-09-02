import { workEn } from '../en/work'

/** zh 字典 key 与 en 严格一一对应（编译期校验，漏 key 报 type error）；zh 保持原文案 */
export const workZh: Record<keyof typeof workEn, string> = {
  // ===== 视图头部 =====
  'work.header.label': 'Work / 作品详情 · {code}',
  'work.notFound': '作品不存在或无权访问',
  'work.backLibrary': '返回作品库',
  'work.backLibraryArrow': '← 返回作品库',
  // ===== 标题 / 标签编辑 =====
  'work.edit.titlePlaceholder': '标题（1~50 字）',
  'work.edit.tagsPlaceholder': '标签，逗号分隔（最多 8 个，每个 1~12 字）',
  'work.edit.saving': '保存中…',
  'work.edit.titleButton': '编辑标题与标签',
  'work.meta.versions': '版本 ×{n}',
  // ===== 版本树 =====
  'work.tree': '版本树',
  'work.tree.current': '当前',
  'work.tree.nodeTitle': '{source} · 候选 ×{n}',
  // ===== 候选列表 =====
  'work.candidates': '候选 / Candidates',
  'work.candidates.hint': '试听低码流 · 采用后可导出',
  'work.candidates.empty': '该版本暂无候选',
  'work.candidate.name': '候选 {label}',
  'work.candidate.untitledWork': '作品',
  'work.candidate.external': '外部模型',
  'work.candidate.quality': 'AI 质量 {n}',
  'work.candidate.adopted': '已定稿',
  'work.candidate.adopt': '采用定稿',
  'work.candidate.segTitle': '{section} · {n} 小节',
  'work.action.preview': '试听',
  // ===== 提示 =====
  'work.toast.adopted': '已采用候选 {label} 为当前版本定稿',
  'work.toast.noPreview': '该候选暂无预览音频',
  'work.toast.titleLength': '标题须为 1~50 字',
  'work.toast.tagsMax': '标签最多 8 个',
  'work.toast.tagLength': '每个标签须为 1~12 字',
  'work.toast.saved': '作品信息已更新',
  // ===== 导出面板 =====
  'work.export.title': '导出与证书',
  'work.export.run': '导出 {format}',
  'work.export.processing': '处理中 {n}%…',
  'work.export.note.wav': '48kHz / 24bit 母带',
  'work.export.note.mp3': '320k CBR',
  'work.export.note.midi': 'melody/chords/bass/drums ×4',
  'work.export.note.stems': 'vocals/drums/bass/other ZIP',
  'work.export.certificate': '下载授权证书 JSON',
  'work.export.generating': '生成中…',
  'work.export.footnote': '导出不扣积分；需先在候选列表「采用定稿」。证书含人类创作留痕与 SHA-256 内容指纹。',
  'work.export.toast.done': '导出完成：{format} 已开始下载（{n} 个文件）',
  'work.export.toast.noFiles': '导出完成，但未返回文件列表',
  'work.export.failed': '导出失败',
  'work.export.toast.pollBroken': '导出任务查询中断',
  'work.export.toast.certStarted': '授权证书 JSON 已开始下载',
}
