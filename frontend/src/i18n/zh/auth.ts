import { authEn } from '../en/auth'

/** auth 命名空间：zh 与 en key 严格一一对应（编译期校验，漏 key 报 type error） */
export const authZh: Record<keyof typeof authEn, string> = {
  // 账号菜单（Sidebar 底部）
  'auth.menu.changePassword': '修改密码',
  'auth.menu.exportData': '导出我的数据',
  'auth.menu.logoutAll': '登出全部设备',
  'auth.menu.deleteAccount': '删除账号',
  // 修改密码弹窗
  'auth.password.title': '修改密码',
  'auth.password.old': '当前密码',
  'auth.password.new': '新密码',
  'auth.password.newPlaceholder': '8~64 位，含字母和数字',
  'auth.password.submit': '更新密码',
  'auth.password.updating': '更新中…',
  'auth.password.changed': '密码已更新',
  'auth.password.required': '请输入当前密码和新密码',
  'auth.password.rule': '新密码需为 8~64 位，且包含字母和数字',
  // 登出全部设备
  'auth.logoutAll.confirmTitle': '登出全部设备？',
  'auth.logoutAll.confirmDesc': '将吊销所有设备上的会话（包括当前设备），并返回产品主页。',
  'auth.logoutAll.confirmText': '全部登出',
  'auth.logoutAll.done': '已在全部设备登出',
  // 导出我的数据（zip）
  'auth.export.started': '数据导出已开始下载',
  'auth.export.preparing': '正在准备导出…',
  // 删除账号（红色警示）
  'auth.delete.title': '删除账号',
  'auth.delete.warn': '将永久删除你的账号及全部作品、音频、积分与审计留痕，此操作不可恢复。',
  'auth.delete.password': '输入密码确认',
  'auth.delete.submit': '永久删除我的账号',
  'auth.delete.deleting': '删除中…',
  'auth.delete.done': '账号已删除，再见。',
  // 忘记密码（LoginView 弹窗）
  'auth.forgot.link': '忘记密码？',
  'auth.forgot.title': '重置密码',
  'auth.forgot.desc': '输入账号邮箱；若该账号存在，我们会向其发送重置链接。',
  'auth.forgot.submit': '发送重置链接',
  'auth.forgot.sending': '发送中…',
  'auth.forgot.sent': '若该账号存在，重置链接已发送至邮箱，请查收',
  'auth.forgot.emailInvalid': '请输入有效的邮箱地址',
  // 重置密码页（#/reset-password?token=…）
  'auth.reset.title': '设置新密码',
  'auth.reset.desc': '你从密码重置邮件链接进入，请在下方设置新密码。',
  'auth.reset.label': '新密码',
  'auth.reset.placeholder': '8~64 位，含字母和数字',
  'auth.reset.submit': '重置密码',
  'auth.reset.submitting': '重置中…',
  'auth.reset.done': '密码已重置，请用新密码登录',
  'auth.reset.invalidToken': '重置链接无效或缺失，请在登录页重新发起找回密码。',
  'auth.reset.backLogin': '← 返回登录',
}
