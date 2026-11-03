import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { login, register, forgotPassword, sendCode } from '../api/auth'
import { useSessionStore } from '../stores/session'
import { useMetaStore } from '../stores/meta'
import { toast } from '../stores/toast'
import { useT } from '../i18n'
import LangSwitch from '../components/common/LangSwitch'
import { Logo } from '../components/common/Logo'
import { SITE_URL } from '../lib/constants'
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
    <div className="modal-overlay">
      <div className="card pop w-[380px] p-6">
        <div className="text-md font-bold">{t('auth.forgot.title')}</div>
        <div className="text-sm mt-2 leading-relaxed text-muted">
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
            <div className="text-xs text-bad">
              {error}
            </div>
          )}
          <div className="flex gap-2 justify-end">
            <button type="button" className="btn btn-ghost btn-md" onClick={onClose}>
              {t('common.cancel')}
            </button>
            <button type="submit" className="btn btn-acc btn-md" disabled={busy}>
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
  const [code, setCode] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const setAuthenticated = useSessionStore((s) => s.setAuthenticated)
  const verifyEnabled = !!useMetaStore((s) => s.meta.email_verification_enabled)
  const navigate = useNavigate()
  const location = useLocation()

  // 验证码发送冷却倒计时（60s 与后端防刷一致）
  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setTimeout(() => setCooldown((n) => n - 1), 1000)
    return () => clearTimeout(timer)
  }, [cooldown])

  const onSendCode = async () => {
    if (cooldown > 0) return
    if (!isEmail(email)) {
      setError(t('login.error.emailInvalid'))
      return
    }
    try {
      await sendCode(email)
      setCodeSent(true)
      setCooldown(60)
      toast(t('login.verify.sent'))
    } catch {
      /* 拦截器已 toast（限流/SMTP 未配置） */
    }
  }

  const from = (location.state as { from?: string } | null)?.from ?? '/studio'

  const validate = (): string | null => {
    if (!isEmail(email)) return t('login.error.emailInvalid')
    if (!password) return t('login.error.passwordRequired')
    if (tab === 'register') {
      if (password.length < 8 || password.length > 64) return t('login.error.passwordLength')
      if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return t('login.error.passwordCharset')
      if (nickname.trim().length < 1 || nickname.trim().length > 24) return t('login.error.nicknameLength')
      if (verifyEnabled && !/^\d{4,8}$/.test(code.trim())) return t('login.verify.required')
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
        data = await register({ email, password, nickname: nickname.trim(),
                                ...(verifyEnabled ? { code: code.trim() } : {}) })
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

  return (
    <div className="login-bg h-screen flex items-center justify-center overflow-hidden">
      {/* 未登录也可切换语言：右上角固定入口 */}
      <div className="absolute top-4 right-4 z-10">
        <LangSwitch />
      </div>
      <div className="w-[380px] pop">
        <div className="flex items-center gap-2 justify-center mb-8">
          <Logo size={26} />
          <div>
            <div className="text-lg font-extrabold tracking-tight leading-none">MELOYU</div>
            <div className="text-2xs mt-1 text-dim">
              {t('login.tagline')}
            </div>
          </div>
        </div>

        <div className="card p-7">
          <div className="flex gap-1.5 mb-5">
            <button type="button" className={`chip ${tab === 'login' ? 'on' : ''}`} onClick={() => setTab('login')}>
              {t('login.tab.login')}
            </button>
            <button type="button" className={`chip ${tab === 'register' ? 'on' : ''}`} onClick={() => setTab('register')}>
              {t('login.tab.register')}
            </button>
          </div>

          <form onSubmit={submit} className="space-y-3">
            {tab === 'register' && (
              <div>
                <div className="text-2xs mb-1 text-dim">
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
              <div className="text-2xs mb-1 text-dim">
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
            {tab === 'register' && verifyEnabled && (
              <div>
                <div className="text-2xs mb-1 text-dim">
                  {t('login.verify.label')}
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    inputMode="numeric"
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                    placeholder={t('login.verify.placeholder')}
                    maxLength={8}
                    className="flex-1 min-w-0"
                  />
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm shrink-0"
                    disabled={cooldown > 0 || loading}
                    onClick={() => void onSendCode()}
                  >
                    {cooldown > 0 ? t('login.verify.resendIn', { n: cooldown }) : t('login.verify.send')}
                  </button>
                </div>
                {codeSent && (
                  <div className="text-2xs mt-1 text-dim">
                    {t('login.verify.sent')}
                  </div>
                )}
              </div>
            )}
            <div>
              <div className="text-2xs mb-1 flex items-center justify-between text-dim">
                <span>{t('login.password.label')}</span>
                {tab === 'login' && (
                  <button
                    type="button"
                    className="font-bold text-acc"
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
              <div className="text-xs leading-relaxed text-bad">
                {error}
              </div>
            )}

            <button type="submit" className="btn btn-acc btn-lg w-full font-bold" disabled={loading}>
              {loading ? t('login.submitting') : tab === 'login' ? t('login.submit.login') : t('login.submit.register')}
            </button>
          </form>

          <div className="mt-5 pt-4 rule-t text-xs leading-relaxed text-dim">
            {/* 2026-09-09  L2/：移除 demo 固定凭据提示与自动填充——生产栈
                启动即禁用种子账号，该凭据已不可用；dev 演示凭据见 backend/README.md。
                商业化发布：不再展示 demo 引擎说明文案 */}
            {/* F7：落地页已迁官网营销站（portal 托管），App 内无 /landing 路由——
                改为外链官网（原 navigate('/landing') 会弹回登录页成死按钮） */}
            <a
              className="mt-3 flex items-center gap-1 transition-colors hover:text-white"
              href={SITE_URL}
              target="_blank"
              rel="noreferrer"
            >
              {t('login.backToLanding')}
            </a>
          </div>
        </div>
      </div>

      <ForgotPasswordModal open={forgotOpen} onClose={() => setForgotOpen(false)} />
    </div>
  )
}
