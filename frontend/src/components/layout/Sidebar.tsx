import { useNavigate, useLocation } from 'react-router-dom'
import { useSessionStore } from '../../stores/session'
import { useUiStore } from '../../stores/ui'
import { PLAN_LABEL, formatNum } from '../../lib/format'

const NAV_GROUPS: Array<{ label: string; items: Array<{ to: string; label: string; kbd: string }> }> = [
  {
    label: '创作',
    items: [
      { to: '/studio', label: '创作工作台', kbd: '1' },
      { to: '/lyrics', label: '歌词助手', kbd: '2' },
    ],
  },
  {
    label: '制作',
    items: [
      { to: '/arrange', label: '编曲', kbd: '3' },
      { to: '/edit', label: '音频剪辑', kbd: '4' },
      { to: '/pitch', label: '修调', kbd: '5' },
    ],
  },
  {
    label: '资产与权利',
    items: [
      { to: '/library', label: '作品库', kbd: '6' },
      { to: '/rights', label: '合规与权利中心', kbd: '7' },
    ],
  },
  {
    label: '账户',
    items: [{ to: '/pricing', label: '定价与积分', kbd: '8' }],
  },
]

/** 212px 侧边栏（对齐原型：logo / 导航分组 / 新手引导 / 积分余额条） */
export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useSessionStore((s) => s.user)
  const logout = useSessionStore((s) => s.logout)
  const startOnboarding = useUiStore((s) => s.startOnboarding)

  const balance = user?.credits.balance ?? 0
  const grant = user?.credits.monthly_grant ?? 0
  const barPct = grant > 0 ? Math.min(100, Math.max(4, (balance / grant) * 100)) : 4

  return (
    <aside
      className="w-[212px] flex-none border-r flex flex-col"
      style={{ borderColor: 'var(--line)', background: 'var(--bg)' }}
    >
      <div className="px-[18px] pt-6 pb-5">
        <div className="flex items-center gap-2 cursor-pointer" onClick={() => navigate('/studio')}>
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
            <rect x="1" y="1" width="20" height="20" stroke="#00ff2c" strokeWidth="2" />
            <rect x="6" y="9" width="3" height="7" fill="#fff" />
            <rect x="11" y="5" width="3" height="11" fill="#00ff2c" />
          </svg>
          <div>
            <div className="text-[15px] font-extrabold tracking-tight leading-none">MELOYU</div>
            <div className="text-[10px] mt-1" style={{ color: 'var(--dim)' }}>
              旋律屿 · 专业 AI 音乐制作
            </div>
          </div>
        </div>
      </div>
      <nav className="rule-t pt-3 flex-1 overflow-y-auto">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <div className="label px-[18px] pt-5 pb-2">{group.label}</div>
            {group.items.map((item) => {
              const on =
                item.to === '/library'
                  ? location.pathname.startsWith('/library') || location.pathname.startsWith('/works')
                  : location.pathname === item.to
              return (
                <div
                  key={item.to}
                  className={`nav-item ${on ? 'on' : ''}`}
                  onClick={() => navigate(item.to)}
                >
                  <span className="dot"></span>
                  {item.label}
                  <span className="kbd">{item.kbd}</span>
                </div>
              )
            })}
          </div>
        ))}
      </nav>
      {/* pb 预留底部固定播放器(68px)的遮挡带，保证积分区与退出按钮可点击 */}
      <div className="rule-t px-[18px] pt-[18px] pb-[84px]">
        <button className="btn btn-ghost w-full !py-1.5 text-[11px] mb-3" onClick={startOnboarding}>
          新手引导
        </button>
        <div className="flex items-center justify-between">
          <span className="label">积分余额</span>
          <span className="text-[11px] font-bold num" style={{ color: 'var(--acc)' }}>
            {formatNum(balance)}
          </span>
        </div>
        <div className="h-[3px] mt-2" style={{ background: 'var(--bg3)' }}>
          <div className="h-full" style={{ width: `${barPct}%`, background: 'var(--acc)' }}></div>
        </div>
        <div className="text-[10px] mt-2 flex items-center justify-between" style={{ color: 'var(--dim)' }}>
          <span>{user ? PLAN_LABEL[user.plan] : '未登录'} · 积分可结转</span>
          <button
            className="font-bold"
            style={{ color: 'var(--dim)' }}
            title="退出登录"
            onClick={() => {
              logout()
              navigate('/login')
            }}
          >
            退出
          </button>
        </div>
      </div>
    </aside>
  )
}
