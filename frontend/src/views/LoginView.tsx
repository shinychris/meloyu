import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { login, register, forgotPassword } from '../api/auth'
import { useSessionStore } from '../stores/session'
import { toast } from '../stores/toast'
import { useT } from '../i18n'
import LangSwitch from '../components/common/LangSwitch'
import type { AuthData } from '../types/api'

type Tab = 'login' | 'register'

function isEmail(v: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)
}

/** 忘记密码弹窗（v0.7.0）：输邮箱 → POST /auth/forgot-password（无论存在与否都 ok，防枚举） */
function ForgotPasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT()
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!open) return null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!isEmail(email)) {
      setError(t('auth.forgot.emailInvalid'))
      return
    }
    setError(null)
    setBusy(true)
    try {
      await forgotPassword({ email })
      // 无论账号是否存在都提示「已发送」，防止账号枚举
      onClose()
      toast(t('auth.forgot.sent'))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center" style={{ background: 'rgba(0,0,0,.72)' }}>
      <div className="card pop w-[380px] p-6">
        <div className="text-[15px] font-bold">{t('auth.forgot.title')}</div>
        <div className="text-[12px] mt-2 leading-relaxed" style={{ color: 'var(--muted)' }}>
          {t('auth.forgot.desc')}
        </div>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
          />
          {error && (
            <div className="text-[11px]" style={{ color: 'var(--bad)' }}>
              {error}
            </div>
          )}
          <div className="flex gap-2 justify-end">
            <button type="button" className="btn btn-ghost !py-1.5 !px-4 text-[12px]" onClick={onClose}>
              {t('common.cancel')}
            </button>
            <button type="submit" className="btn btn-acc !py-1.5 !px-4 text-[12px]" disabled={busy}>
              {busy ? t('auth.forgot.sending') : t('auth.forgot.submit')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

/** 登录/注册页（原型未含，按同一设计令牌扩展的暗色极简页） */
export default function LoginView() {
  const t = useT()
  const [tab, setTab] = useState<Tab>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [nickname, setNickname] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [forgotOpen, setForgotOpen] = useState(false)
  const setAuthenticated = useSessionStore((s) => s.setAuthenticated)
  const navigate = useNavigate()
  const location = useLocation()

  const from = (location.state as { from?: string } | null)?.from ?? '/studio'

  const validate = (): string | null => {
    if (!isEmail(email)) return t('login.error.emailInvalid')
    if (!password) return t('login.error.passwordRequired')
    if (tab === 'register') {
      if (password.length < 8 || password.length > 64) return t('login.error.passwordLength')
      if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return t('login.error.passwordCharset')
      if (nickname.trim().length < 1 || nickname.trim().length > 24) return t('login.error.nicknameLength')
    }
    return null
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const err = validate()
    if (err) {
      setError(err)
      return
    }
    setError(null)
    setLoading(true)
    try {
      let data: AuthData
      if (tab === 'login') {
        data = await login({ email, password })
      } else {
        data = await register({ email, password, nickname: nickname.trim() })
      }
      setAuthenticated(data)
      navigate(from, { replace: true })
    } catch {
      /* 拦截器已 toast（40103 邮箱或密码错误 / 40901 已注册等） */
      setError(t('login.error.failed'))
    } finally {
      setLoading(false)
    }
  }

  const fillDemo = () => {
    setTab('login')
    setEmail('demo@meloyu.local')
    setPassword('Meloyu2026')
    setError(null)
  }

  return (
    <div className="login-bg h-screen flex items-center justify-center overflow-hidden">
      {/* 未登录也可切换语言：右上角固定入口 */}
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
          <div className="flex gap-1.5 mb-5">
            <span className={`chip ${tab === 'login' ? 'on' : ''}`} onClick={() => setTab('login')}>
              {t('login.tab.login')}
            </span>
            <span className={`chip ${tab === 'register' ? 'on' : ''}`} onClick={() => setTab('register')}>
              {t('login.tab.register')}
            </span>
          </div>

          <form onSubmit={submit} className="space-y-3">
            {tab === 'register' && (
              <div>
                <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>
                  {t('login.nickname.label')}
                </div>
                <input
                  type="text"
                  value={nickname}
                  onChange={(e) => setNickname(e.target.value)}
                  placeholder={t('login.nickname.placeholder')}
                  maxLength={24}
                />
              </div>
            )}
            <div>
              <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>
                {t('login.email.label')}
              </div>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </div>
            <div>
              <div className="text-[10px] mb-1 flex items-center justify-between" style={{ color: 'var(--dim)' }}>
                <span>{t('login.password.label')}</span>
                {tab === 'login' && (
                  <button
                    type="button"
                    className="font-bold"
                    style={{ color: 'var(--acc)' }}
                    onClick={() => setForgotOpen(true)}
                  >
                    {t('auth.forgot.link')}
                  </button>
                )}
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={tab === 'register' ? t('login.password.placeholderRegister') : t('login.password.placeholder')}
                autoComplete={tab === 'login' ? 'current-password' : 'new-password'}
              />
            </div>

            {error && (
              <div className="text-[11px] leading-relaxed" style={{ color: 'var(--bad)' }}>
                {error}
              </div>
            )}

            <button type="submit" className="btn btn-acc w-full !py-3 text-[13px] font-bold" disabled={loading}>
              {loading ? t('login.submitting') : tab === 'login' ? t('login.submit.login') : t('login.submit.register')}
            </button>
          </form>

          <div className="mt-5 pt-4 rule-t text-[11px] leading-relaxed" style={{ color: 'var(--dim)' }}>
            {t('login.demo.account')}
            <span className="num" style={{ color: 'var(--muted)' }}>
              demo@meloyu.local / Meloyu2026
            </span>
            <button className="text-[11px] font-bold ml-2" style={{ color: 'var(--acc)' }} type="button" onClick={fillDemo}>
              {t('login.demo.fill')}
            </button>
            <div className="mt-1">{t('login.demo.note')}</div>
            <button
              className="mt-3 flex items-center gap-1 transition-colors hover:text-white"
              type="button"
              onClick={() => navigate('/landing')}
            >
              {t('login.backToLanding')}
            </button>
          </div>
        </div>
      </div>

      <ForgotPasswordModal open={forgotOpen} onClose={() => setForgotOpen(false)} />
    </div>
  )
}
