import { commonEn } from '../en/common'

/** zh 字典 key 与 en 严格一一对应（编译期校验，漏 key 报 type error） */
export const commonZh: Record<keyof typeof commonEn, string> = {
  'common.confirm': '确认',
  'common.cancel': '取消',
  'common.save': '保存',
  'common.delete': '删除',
  'common.close': '关闭',
  'common.retry': '重试',
  'common.search': '搜索',
  'common.loading': '载入中…',
  'common.copy': '复制',
  'common.copied': '已复制',
  'common.download': '下载',
  'common.back': '返回',
  'common.next': '下一步',
  'common.done': '完成',
  'common.edit': '编辑',
  'common.view': '查看',
  'common.all': '全部',
  'common.total': '共 {n} 条',
  'common.empty': '暂无内容',
  'common.language': '语言',
}
