import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { resetPassword } from '../api/auth'
import { toast } from '../stores/toast'
import { useT } from '../i18n'
import LangSwitch from '../components/common/LangSwitch'

/** 新密码规则：8+ 位字母 + 数字（与注册口径一致） */
function isValidPassword(v: string): boolean {
  return v.length >= 8 && v.length <= 64 && /[A-Za-z]/.test(v) && /\d/.test(v)
}

/**
 * 重置密码页（#/reset-password?token=xxx，从邮件链接进入）。
 * 独立路由（无鉴权）：读 query token → 新密码表单 → POST /auth/reset-password
 * 成功后提示并跳登录。token 缺失时给出失效提示与回登录入口。
 */
export default function ResetPasswordView() {
  const t = useT()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const token = params.get('token')?.trim() ?? ''
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!isValidPassword(password)) {
      setError(t('auth.password.rule'))
      return
    }
    setError(null)
    setBusy(true)
    try {
      await resetPassword({ token, new_password: password })
      setDone(true)
      toast(t('auth.reset.done'))
      window.setTimeout(() => navigate('/login', { replace: true }), 1600)
    } catch {
      /* 拦截器已 toast（token 失效 / 密码规则不符等） */
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-bg h-screen flex items-center justify-center overflow-hidden">
      <div className="absolute top-4 right-4 z-10">
        <LangSwitch />
      </div>
      <div className="w-[380px] pop">
        <div className="flex items-center gap-2 justify-center mb-8">
          <svg width="26" height="26" viewBox="0 0 22 22" fill="none">
            <rect x="1" y="1" width="20" height="20" stroke="#00ff2c" strokeWidth="2" />
            <rect x="6" y="9" width="3" height="7" fill="#fff" />
            <rect x="11" y="5" width="3" height="11" fill="#00ff2c" />
          </svg>
          <div>
            <div className="text-[17px] font-extrabold tracking-tight leading-none">MELOYU</div>
            <div className="text-[10px] mt-1" style={{ color: 'var(--dim)' }}>
              {t('login.tagline')}
            </div>
          </div>
        </div>

        <div className="card p-7">
          {!token ? (
            // 链接缺 token：不可提交，引导回登录页重新发起
            <>
              <div className="text-[16px] font-bold">{t('auth.reset.title')}</div>
              <div className="text-[12px] mt-3 leading-relaxed" style={{ color: 'var(--warn)' }}>
                {t('auth.reset.invalidToken')}
              </div>
              <Link to="/login" className="block mt-5 text-[12px] font-bold" style={{ color: 'var(--acc)' }}>
                {t('auth.reset.backLogin')}
              </Link>
            </>
          ) : done ? (
            <>
              <div className="text-[16px] font-bold">{t('auth.reset.done')}</div>
              <Link to="/login" className="block mt-5 text-[12px] font-bold" style={{ color: 'var(--acc)' }}>
                {t('auth.reset.backLogin')}
              </Link>
            </>
          ) : (
            <form onSubmit={submit} className="space-y-3">
              <div className="text-[16px] font-bold">{t('auth.reset.title')}</div>
              <div className="text-[11px] leading-relaxed" style={{ color: 'var(--dim)' }}>
                {t('auth.reset.desc')}
              </div>
              <div>
                <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>
                  {t('auth.reset.label')}
                </div>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t('auth.reset.placeholder')}
                  autoComplete="new-password"
                  autoFocus
                />
              </div>
              {error && (
                <div className="text-[11px] leading-relaxed" style={{ color: 'var(--bad)' }}>
                  {error}
                </div>
              )}
              <button type="submit" className="btn btn-acc w-full !py-3 text-[13px] font-bold" disabled={busy}>
                {busy ? t('auth.reset.submitting') : t('auth.reset.submit')}
              </button>
              <Link to="/login" className="block text-[11px] font-bold" style={{ color: 'var(--muted)' }}>
                {t('auth.reset.backLogin')}
              </Link>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
