/**
 * auth 命名空间：v0.7.0 账号中心（Sidebar 账号菜单 / 修改密码 / 登出全部设备 /
 * 导出数据 / 删除账号）与密码找回（LoginView 忘记密码 / ResetPasswordView）。
 */
export const authEn = {
  // 账号菜单（Sidebar 底部）
  'auth.menu.changePassword': 'Change password',
  'auth.menu.exportData': 'Export my data',
  'auth.menu.logoutAll': 'Sign out all devices',
  'auth.menu.deleteAccount': 'Delete account',
  // 修改密码弹窗
  'auth.password.title': 'Change password',
  'auth.password.old': 'Current password',
  'auth.password.new': 'New password',
  'auth.password.newPlaceholder': '8–64 characters, letters and numbers',
  'auth.password.submit': 'Update password',
  'auth.password.updating': 'Updating…',
  'auth.password.changed': 'Password updated',
  'auth.password.required': 'Enter your current and new password',
  'auth.password.rule': 'New password must be 8–64 characters, with letters and numbers',
  // 登出全部设备
  'auth.logoutAll.confirmTitle': 'Sign out all devices?',
  'auth.logoutAll.confirmDesc':
    'This revokes the session on every device, including this one, and returns you to the home page.',
  'auth.logoutAll.confirmText': 'Sign out everywhere',
  'auth.logoutAll.done': 'Signed out on all devices',
  // 导出我的数据（zip）
  'auth.export.started': 'Data export download started',
  'auth.export.preparing': 'Preparing export…',
  // 删除账号（红色警示）
  'auth.delete.title': 'Delete account',
  'auth.delete.warn':
    'This permanently deletes your account together with all works, audio files, credits and audit trails. This cannot be undone.',
  'auth.delete.password': 'Confirm with your password',
  'auth.delete.submit': 'Delete my account permanently',
  'auth.delete.deleting': 'Deleting…',
  'auth.delete.done': 'Account deleted. Goodbye.',
  // 忘记密码（LoginView 弹窗）
  'auth.forgot.link': 'Forgot password?',
  'auth.forgot.title': 'Reset your password',
  'auth.forgot.desc': 'Enter your account email; if it exists, we will send a reset link to it.',
  'auth.forgot.submit': 'Send reset link',
  'auth.forgot.sending': 'Sending…',
  'auth.forgot.sent': 'If the account exists, a reset link has been sent to your inbox',
  'auth.forgot.emailInvalid': 'Enter a valid email address',
  // 重置密码页（#/reset-password?token=…）
  'auth.reset.title': 'Set a new password',
  'auth.reset.desc': 'You arrived from the password-reset email. Enter a new password below.',
  'auth.reset.label': 'New password',
  'auth.reset.placeholder': '8–64 characters, letters and numbers',
  'auth.reset.submit': 'Reset password',
  'auth.reset.submitting': 'Resetting…',
  'auth.reset.done': 'Password has been reset — please sign in with the new password',
  'auth.reset.invalidToken': 'This reset link is invalid or missing. Request a new one from the sign-in page.',
  'auth.reset.backLogin': '← Back to sign in',
} as const
