/** library 命名空间：作品库（LibraryView） */
export const libraryEn = {
  // 视图头部
  'library.header.label': 'Library / Works',
  'library.title.all': 'All works',
  'library.title.trash': 'Trash',
  'library.search.placeholder': 'Search titles / lyrics…',
  'library.sort.title': 'Sort field',
  'library.sort.updated': 'Last updated',
  'library.sort.created': 'Date created',
  'library.order.title': 'Sort direction',
  'library.order.desc': 'Descending',
  'library.order.asc': 'Ascending',
  // 筛选 chips
  'library.filter.all': 'All {n}',
  'library.filter.draft': 'Drafts',
  'library.filter.fav': 'Starred',
  'library.filter.trash': 'Trash',
  // 表头
  'library.col.no': 'No.',
  'library.col.cover': 'Cover',
  'library.col.title': 'Title',
  'library.col.key': 'Key',
  'library.col.bpm': 'BPM',
  'library.col.export': 'Export',
  'library.col.license': 'License',
  // 列表 / 空状态
  'library.empty.title': 'No works yet',
  'library.empty.hint': 'Head to the Studio and generate your first song',
  'library.empty.cta': 'Open Studio →',
  'library.empty.trashTitle': 'Trash is empty',
  'library.empty.trashHint': 'Deleted works are kept here for 30 days',
  'library.trashBadge': 'In trash',
  'library.export.none': 'Not exported',
  'library.license.commercial': 'Commercial license',
  'library.license.nonCommercial': 'Non-commercial',
  // 行内操作
  'library.action.preview': 'Preview',
  'library.action.restore': 'Restore',
  'library.action.permanentDelete': 'Delete permanently',
  'library.action.trash': 'Move to trash',
  'library.fav.add': 'Star',
  'library.fav.remove': 'Unstar',
  // 确认弹窗
  'library.confirm.trashTitle': 'Move "{title}" to trash?',
  'library.confirm.trashDesc':
    'The work will stay in trash for 30 days and can be restored anytime; generated versions and audio are unaffected.',
  'library.confirm.deleteTitle': 'Permanently delete "{title}"?',
  'library.confirm.deleteDesc':
    'This cascades to every version, candidate, and audio file, and cannot be recovered. This action is irreversible.',
  // 提示
  'library.toast.restored': 'Restored "{title}"',
  'library.toast.trashed': 'Moved "{title}" to trash',
  'library.toast.deleted': 'Permanently deleted',
  'library.toast.noPreview': 'No preview audio for this work yet (no candidate adopted)',
} as const
