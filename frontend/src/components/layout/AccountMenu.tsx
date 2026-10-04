import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { changePassword, deleteAccount, exportData, logoutAll } from '../../api/auth'
import { saveBlob } from '../../api/client'
import { useSessionStore } from '../../stores/session'
import { confirmDialog } from '../../stores/confirm'
import { toast } from '../../stores/toast'
import { planLabel } from '../../lib/format'
import { useT } from '../../i18n'

/** 新密码规则：8~64 位且同时包含字母与数字（与注册口径一致） */
function isValidNewPassword(v: string): boolean {
  return v.length >= 8 && v.length <= 64 && /[A-Za-z]/.test(v) && /\d/.test(v)
}

/** 修改密码弹窗（账号菜单） */
function ChangePasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT()
  const [oldPwd, setOldPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open) {
      setOldPwd('')
      setNewPwd('')
      setError(null)
    }
  }, [open])

  if (!open) return null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!oldPwd || !newPwd) {
      setError(t('auth.password.required'))
      return
    }
    if (!isValidNewPassword(newPwd)) {
      setError(t('auth.password.rule'))
      return
    }
    setError(null)
    setBusy(true)
    try {
      await changePassword({ old_password: oldPwd, new_password: newPwd })
      toast(t('auth.password.changed'))
      onClose()
    } catch {
      /* 拦截器已 toast（旧密码错误等） */
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="card pop w-[380px] p-6">
        <div className="text-md font-bold">{t('auth.password.title')}</div>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <div>
            <div className="text-2xs mb-1 text-dim">
              {t('auth.password.old')}
            </div>
            <input
              type="password"
              value={oldPwd}
              onChange={(e) => setOldPwd(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div>
            <div className="text-2xs mb-1 text-dim">
              {t('auth.password.new')}
            </div>
            <input
              type="password"
              value={newPwd}
              onChange={(e) => setNewPwd(e.target.value)}
              placeholder={t('auth.password.newPlaceholder')}
              autoComplete="new-password"
            />
          </div>
          {error && (
            <div className="text-xs leading-relaxed text-bad">
              {error}
            </div>
          )}
          <div className="flex gap-2 justify-end pt-1">
            <button type="button" className="btn btn-ghost btn-md" onClick={onClose}>
              {t('common.cancel')}
            </button>
            <button type="submit" className="btn btn-acc btn-md" disabled={busy}>
              {busy ? t('auth.password.updating') : t('auth.password.submit')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

/** 删除账号弹窗：红色警示 + 输密码确认（复用 ConfirmDialog 的视觉模式） */
function DeleteAccountModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT()
  const navigate = useNavigate()
  const logout = useSessionStore((s) => s.logout)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open) {
      setPassword('')
      setError(null)
    }
  }, [open])

  if (!open) return null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!password) {
      setError(t('auth.delete.password'))
      return
    }
    setError(null)
    setBusy(true)
    try {
      await deleteAccount({ password })
      toast(t('auth.delete.done'))
      logout() // 清 token / 停轮询 / 停播放器
      navigate('/landing', { replace: true })
    } catch {
      /* 拦截器已 toast（密码错误 / 会话过期等） */
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="card pop w-[400px] p-6" style={{ borderColor: 'var(--bad)' }}>
        <div className="text-md font-bold text-bad">
          {t('auth.delete.title')}
        </div>
        <div className="text-sm mt-2 leading-relaxed text-muted">
          {t('auth.delete.warn')}
        </div>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <div>
            <div className="text-2xs mb-1 text-dim">
              {t('auth.delete.password')}
            </div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          {error && (
            <div className="text-xs text-bad">
              {error}
            </div>
          )}
          <div className="flex gap-2 justify-end pt-1">
            <button type="button" className="btn btn-ghost btn-md" onClick={onClose}>
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              className="btn btn-md"
              style={{ borderColor: 'var(--bad)', color: 'var(--bad)' }}
              disabled={busy}
            >
              {busy ? t('auth.delete.deleting') : t('auth.delete.submit')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

/**
 * 账号管理区（Sidebar 底部用户区弹出菜单，v0.7.0）：
 * 修改密码 / 导出我的数据 / 登出全部设备 / 删除账号 / 登出（本机）。
 * 视觉跟随现有直角/暗色/荧光绿令牌；确认类弹窗复用 ConfirmDialog 与其视觉模式。
 */
export default function AccountMenu() {
  const t = useT()
  const navigate = useNavigate()
  const user = useSessionStore((s) => s.user)
  const logout = useSessionStore((s) => s.logout)
  const license = useSessionStore((s) => s.license)
  const [open, setOpen] = useState(false)
  const [pwdOpen, setPwdOpen] = useState(false)
  const [delOpen, setDelOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  // v0.16.0：desktop 形态免登录（本地档案），账号类菜单项收敛为数据导出
  const isDesktop = license?.mode === 'desktop'

  // 点击菜单外任意处关闭（弹窗在 fixed 层，不受影响）
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  /** 登出全部设备：吊销 refresh token（含本机），清 token 跳落地页 */
  const onLogoutAll = async () => {
    setOpen(false)
    const ok = await confirmDialog({
      title: t('auth.logoutAll.confirmTitle'),
      description: t('auth.logoutAll.confirmDesc'),
      confirmText: t('auth.logoutAll.confirmText'),
      danger: true,
    })
    if (!ok) return
    try {
      await logoutAll()
    } catch {
      /* 即使后端失败也继续本地登出（token 已可能失效） */
    }
    toast(t('auth.logoutAll.done'))
    logout()
    navigate('/landing', { replace: true })
  }

  /** 导出我的数据：GET /auth/export-data（zip 流）→ a[download] 保存 */
  const onExport = async () => {
    setOpen(false)
    if (exporting) return
    setExporting(true)
    toast(t('auth.export.preparing'))
    try {
      const blob = await exportData()
      saveBlob(blob, `meloyu-data-export-${new Date().toISOString().slice(0, 10)}.zip`)
      toast(t('auth.export.started'))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setExporting(false)
    }
  }

  const onLogout = () => {
    setOpen(false)
    logout()
    navigate('/login')
  }

  return (
    <div className="relative mt-2" ref={wrapRef}>
      <div className="text-2xs flex items-center justify-between text-dim">
        <span className="acc-plan truncate">
          {isDesktop
            ? t('license.menu.planLabel')
            : user
              ? `${planLabel(user.plan)} · ${t('app.sidebar.transferable')}`
              : `${t('app.sidebar.notLoggedIn')} · ${t('app.sidebar.transferable')}`}
        </span>
        {!isDesktop && (
          <button
            className="acc-trigger font-bold flex-none ml-1"
            style={{ color: open ? 'var(--acc)' : 'var(--dim)' }}
            title={t('app.sidebar.logoutTitle')}
            onClick={() => setOpen((v) => !v)}
          >
            {t('app.sidebar.logout')} ▾
          </button>
        )}
        {isDesktop && (
          <button
            className="acc-trigger font-bold flex-none ml-1"
            style={{ color: 'var(--dim)' }}
            title={t('auth.menu.exportData')}
            onClick={() => void onExport()}
          >
            {exporting ? t('auth.export.preparing') : '⇩'}
          </button>
        )}
      </div>

      {open && !isDesktop && (
        <div className="accmenu">
          <button className="accmenu-item" onClick={() => { setOpen(false); setPwdOpen(true) }}>
            {t('auth.menu.changePassword')}
          </button>
          <button className="accmenu-item" onClick={() => void onExport()}>
            {exporting ? t('auth.export.preparing') : t('auth.menu.exportData')}
          </button>
          <button className="accmenu-item" onClick={() => void onLogoutAll()}>
            {t('auth.menu.logoutAll')}
          </button>
          <div className="h-px mx-2 bg-line"></div>
          <button className="accmenu-item danger" onClick={() => { setOpen(false); setDelOpen(true) }}>
            {t('auth.menu.deleteAccount')}
          </button>
          <div className="h-px mx-2 bg-line"></div>
          <button className="accmenu-item" onClick={onLogout}>
            {t('app.sidebar.logout')}
          </button>
        </div>
      )}

      <ChangePasswordModal open={pwdOpen} onClose={() => setPwdOpen(false)} />
      <DeleteAccountModal open={delOpen} onClose={() => setDelOpen(false)} />
    </div>
  )
}
