import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { login, register } from '../api/auth'
import { useSessionStore } from '../stores/session'
import type { AuthData } from '../types/api'

type Tab = 'login' | 'register'

function isEmail(v: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)
}

/** 登录/注册页（原型未含，按同一设计令牌扩展的暗色极简页） */
export default function LoginView() {
  const [tab, setTab] = useState<Tab>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [nickname, setNickname] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const setAuthenticated = useSessionStore((s) => s.setAuthenticated)
  const navigate = useNavigate()
  const location = useLocation()

  const from = (location.state as { from?: string } | null)?.from ?? '/studio'

  const validate = (): string | null => {
    if (!isEmail(email)) return '请输入有效的邮箱地址'
    if (!password) return '请输入密码'
    if (tab === 'register') {
      if (password.length < 8 || password.length > 64) return '密码需为 8~64 位，且包含字母和数字'
      if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return '密码需同时包含字母和数字'
      if (nickname.trim().length < 1 || nickname.trim().length > 24) return '昵称需为 1~24 字'
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
      setError('登录/注册失败，请检查输入')
    } finally {
      setLoading(false)
    }
  }

  const fillDemo = () => {
    setTab('login')
    setEmail('demo@meloyu.local')
    setPassword('Demo123456!')
    setError(null)
  }

  return (
    <div className="login-bg h-screen flex items-center justify-center overflow-hidden">
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
              旋律屿 · 专业 AI 音乐制作
            </div>
          </div>
        </div>

        <div className="card p-7">
          <div className="flex gap-1.5 mb-5">
            <span className={`chip ${tab === 'login' ? 'on' : ''}`} onClick={() => setTab('login')}>
              登录
            </span>
            <span className={`chip ${tab === 'register' ? 'on' : ''}`} onClick={() => setTab('register')}>
              注册
            </span>
          </div>

          <form onSubmit={submit} className="space-y-3">
            {tab === 'register' && (
              <div>
                <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>
                  昵称
                </div>
                <input
                  type="text"
                  value={nickname}
                  onChange={(e) => setNickname(e.target.value)}
                  placeholder="作品署名用，如：岛民"
                  maxLength={24}
                />
              </div>
            )}
            <div>
              <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>
                邮箱
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
              <div className="text-[10px] mb-1" style={{ color: 'var(--dim)' }}>
                密码
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={tab === 'register' ? '8~64 位，含字母和数字' : '密码'}
                autoComplete={tab === 'login' ? 'current-password' : 'new-password'}
              />
            </div>

            {error && (
              <div className="text-[11px] leading-relaxed" style={{ color: 'var(--bad)' }}>
                {error}
              </div>
            )}

            <button type="submit" className="btn btn-acc w-full !py-3 text-[13px] font-bold" disabled={loading}>
              {loading ? '请稍候…' : tab === 'login' ? '登录工作台' : '注册并赠送 200 积分'}
            </button>
          </form>

          <div className="mt-5 pt-4 rule-t text-[11px] leading-relaxed" style={{ color: 'var(--dim)' }}>
            演示账号：<span className="num" style={{ color: 'var(--muted)' }}>demo@meloyu.local / Demo123456!</span>
            <button className="text-[11px] font-bold ml-2" style={{ color: 'var(--acc)' }} type="button" onClick={fillDemo}>
              一键填入
            </button>
            <div className="mt-1">本地演示引擎 · 生成内容自动登记创作留痕</div>
          </div>
        </div>
      </div>
    </div>
  )
}
