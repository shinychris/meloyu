/**
 * 通用文案（跨页面复用的按钮 / 状态词）。模块专属文案请放各自模块字典，
 * 允许与 common 轻度重复，避免为共享一个词跨模块耦合。
 */
export const commonEn = {
  'common.confirm': 'Confirm',
  'common.cancel': 'Cancel',
  'common.save': 'Save',
  'common.delete': 'Delete',
  'common.close': 'Close',
  'common.retry': 'Retry',
  'common.search': 'Search',
  'common.loading': 'Loading…',
  'common.copy': 'Copy',
  'common.copied': 'Copied',
  'common.download': 'Download',
  'common.back': 'Back',
  'common.next': 'Next',
  'common.done': 'Done',
  'common.edit': 'Edit',
  'common.view': 'View',
  'common.all': 'All',
  'common.total': 'Total {n}',
  'common.empty': 'Nothing here yet',
  'common.language': 'Language',
  // 语言切换下拉选项全名（按当前界面语言渲染；en 侧对中文用英文名，界面零中文）
  'common.lang.en': 'English',
  'common.lang.zh': 'Chinese (Simplified)',
} as const
