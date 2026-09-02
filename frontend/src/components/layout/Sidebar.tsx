import { useNavigate, useLocation } from 'react-router-dom'
import { useSessionStore } from '../../stores/session'
import { useUiStore } from '../../stores/ui'
import { formatNum } from '../../lib/format'
import { useT } from '../../i18n'
import LangSwitch from '../common/LangSwitch'
import AccountMenu from './AccountMenu'
import type { TranslationKey } from '../../i18n'

const NAV_GROUPS: Array<{
  labelKey: TranslationKey
  items: Array<{ to: string; labelKey: TranslationKey; kbd: string }>
}> = [
  {
    labelKey: 'app.sidebar.group.create',
    items: [
      { to: '/studio', labelKey: 'app.sidebar.nav.studio', kbd: '1' },
      { to: '/lyrics', labelKey: 'app.sidebar.nav.lyrics', kbd: '2' },
    ],
  },
  {
    labelKey: 'app.sidebar.group.produce',
    items: [
      { to: '/arrange', labelKey: 'app.sidebar.nav.arrange', kbd: '3' },
      { to: '/edit', labelKey: 'app.sidebar.nav.edit', kbd: '4' },
      { to: '/pitch', labelKey: 'app.sidebar.nav.pitch', kbd: '5' },
    ],
  },
  {
    labelKey: 'app.sidebar.group.assets',
    items: [
      { to: '/library', labelKey: 'app.sidebar.nav.library', kbd: '6' },
      { to: '/rights', labelKey: 'app.sidebar.nav.rights', kbd: '7' },
    ],
  },
  {
    labelKey: 'app.sidebar.group.account',
    items: [
      { to: '/pricing', labelKey: 'app.sidebar.nav.pricing', kbd: '8' },
      { to: '/models', labelKey: 'app.sidebar.nav.models', kbd: '9' },
    ],
  },
]

/** 212px 侧边栏（对齐原型：logo / 导航分组 / 新手引导 / 积分余额条 / 账号菜单） */
export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const t = useT()
  const user = useSessionStore((s) => s.user)
  const startOnboarding = useUiStore((s) => s.startOnboarding)

  const balance = user?.credits.balance ?? 0
  const grant = user?.credits.monthly_grant ?? 0
  const barPct = grant > 0 ? Math.min(100, Math.max(4, (balance / grant) * 100)) : 4

  return (
    <aside
      className="sidebar w-[212px] flex-none border-r flex flex-col"
      style={{ borderColor: 'var(--line)', background: 'var(--bg)' }}
    >
      <div className="sidebar-head px-[18px] pt-6 pb-5">
        <div className="flex items-center gap-2 cursor-pointer" onClick={() => navigate('/studio')}>
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
            <rect x="1" y="1" width="20" height="20" stroke="#00ff2c" strokeWidth="2" />
            <rect x="6" y="9" width="3" height="7" fill="#fff" />
            <rect x="11" y="5" width="3" height="11" fill="#00ff2c" />
          </svg>
          <div className="sidebar-head-text">
            <div className="text-[15px] font-extrabold tracking-tight leading-none">MELOYU</div>
            <div className="text-[10px] mt-1" style={{ color: 'var(--dim)' }}>
              {t('app.sidebar.tagline')}
            </div>
          </div>
        </div>
      </div>
      <nav className="rule-t pt-3 flex-1 overflow-y-auto">
        {NAV_GROUPS.map((group) => (
          <div key={group.labelKey}>
            <div className="label px-[18px] pt-5 pb-2">{t(group.labelKey)}</div>
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
                  {t(item.labelKey)}
                  <span className="kbd">{item.kbd}</span>
                </div>
              )
            })}
          </div>
        ))}
      </nav>
      {/* pb 预留底部固定播放器(68px)的遮挡带，保证积分区与账号菜单可点击 */}
      <div className="sidebar-bottom rule-t px-[18px] pt-[18px] pb-[84px]">
        <button className="btn btn-ghost w-full !py-1.5 text-[11px] mb-3" onClick={startOnboarding}>
          {t('app.sidebar.onboarding')}
        </button>
        <div className="flex items-center justify-between">
          <span className="label">{t('app.sidebar.credits')}</span>
          <span className="text-[11px] font-bold num" style={{ color: 'var(--acc)' }}>
            {formatNum(balance)}
          </span>
        </div>
        <div className="h-[3px] mt-2" style={{ background: 'var(--bg3)' }}>
          <div className="h-full" style={{ width: `${barPct}%`, background: 'var(--acc)' }}></div>
        </div>
        {/* 账号管理区：档位行 + 弹出菜单（改密/导出/登出全部/删号/登出） */}
        <AccountMenu />
        <div className="mt-3 flex sidebar-lang">
          <LangSwitch />
        </div>
      </div>
    </aside>
  )
}
