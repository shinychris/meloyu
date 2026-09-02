import { libraryEn } from '../en/library'

/** zh 字典 key 与 en 严格一一对应（编译期校验，漏 key 报 type error）；zh 保持原文案 */
export const libraryZh: Record<keyof typeof libraryEn, string> = {
  // ===== 视图头部 =====
  'library.header.label': 'Library / 作品库',
  'library.title.all': '全部作品',
  'library.title.trash': '回收站',
  'library.search.placeholder': '搜索标题 / 歌词…',
  'library.sort.title': '排序字段',
  'library.sort.updated': '最近更新',
  'library.sort.created': '创建时间',
  'library.order.title': '排序方向',
  'library.order.desc': '降序',
  'library.order.asc': '升序',
  // ===== 筛选 chips =====
  'library.filter.all': '全部 {n}',
  'library.filter.draft': '草稿',
  'library.filter.fav': '已收藏',
  'library.filter.trash': '回收站',
  // ===== 表头 =====
  'library.col.no': '编号',
  'library.col.cover': '封面',
  'library.col.title': '标题',
  'library.col.key': '调性',
  'library.col.bpm': 'BPM',
  'library.col.export': '导出',
  'library.col.license': '授权',
  // ===== 列表 / 空状态 =====
  'library.empty.title': '还没有作品',
  'library.empty.hint': '去创作工作台生成你的第一首歌',
  'library.empty.cta': '进入工作台 →',
  'library.empty.trashTitle': '回收站是空的',
  'library.empty.trashHint': '删除的作品会在这里保留 30 天',
  'library.trashBadge': '回收站',
  'library.export.none': '未导出',
  'library.license.commercial': '商用授权',
  'library.license.nonCommercial': '非商用',
  // ===== 行内操作 =====
  'library.action.preview': '试听',
  'library.action.restore': '恢复',
  'library.action.permanentDelete': '永久删除',
  'library.action.trash': '移入回收站',
  'library.fav.add': '收藏',
  'library.fav.remove': '取消收藏',
  // ===== 确认弹窗 =====
  'library.confirm.trashTitle': '移入回收站「{title}」？',
  'library.confirm.trashDesc': '作品将进入回收站并保留 30 天，期间可随时恢复；已生成的版本与音频不受影响。',
  'library.confirm.deleteTitle': '永久删除「{title}」？',
  'library.confirm.deleteDesc': '将级联删除全部版本、候选与音频文件，不可恢复。此操作不可撤销。',
  // ===== 提示 =====
  'library.toast.restored': '已恢复「{title}」',
  'library.toast.trashed': '已将「{title}」移入回收站',
  'library.toast.deleted': '已永久删除',
  'library.toast.noPreview': '该作品暂无预览音频（尚未采用候选）',
}
