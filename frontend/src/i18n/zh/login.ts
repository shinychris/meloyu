import { loginEn } from '../en/login'

/** zh 字典 key 与 en 严格一一对应（编译期校验，漏 key 报 type error） */
export const loginZh: Record<keyof typeof loginEn, string> = {
  'login.tagline': '旋律屿 · 专业 AI 音乐制作',
  'login.tab.login': '登录',
  'login.tab.register': '注册',
  'login.nickname.label': '昵称',
  'login.nickname.placeholder': '作品署名用，如：岛民',
  'login.email.label': '邮箱',
  'login.password.label': '密码',
  'login.password.placeholder': '密码',
  'login.password.placeholderRegister': '8~64 位，含字母和数字',
  'login.error.emailInvalid': '请输入有效的邮箱地址',
  'login.error.passwordRequired': '请输入密码',
  'login.error.passwordLength': '密码需为 8~64 位，且包含字母和数字',
  'login.error.passwordCharset': '密码需同时包含字母和数字',
  'login.error.nicknameLength': '昵称需为 1~24 字',
  'login.error.failed': '登录/注册失败，请检查输入',
  'login.submitting': '请稍候…',
  'login.submit.login': '登录工作台',
  'login.submit.register': '注册并赠送 200 积分',
  'login.demo.account': '演示账号：',
  'login.demo.fill': '一键填入',
  'login.demo.note': '本地演示引擎 · 生成内容自动登记创作留痕',
  'login.backToLanding': '← 返回产品主页',
}
