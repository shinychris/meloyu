import { useNavigate, useLocation } from 'react-router-dom'
import { useSessionStore } from '../../stores/session'
import { useUiStore } from '../../stores/ui'
import { formatNum } from '../../lib/format'
import { useT } from '../../i18n'
import LangSwitch from '../common/LangSwitch'
import { Logo } from '../common/Logo'
import AccountMenu from './AccountMenu'
import type { TranslationKey } from '../../i18n'

const NAV_GROUPS: Array<{
  labelKey: TranslationKey
  items: Array<{ to: string; labelKey: TranslationKey; kbd?: string }>
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
      { to: '/market', labelKey: 'app.sidebar.nav.market', kbd: '0' },
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

/** 212px 侧边栏（对齐原型：logo / 导航分组 / 新手引导 / 授权徽标 / 账号菜单）。
 *  v0.16.0：license 模式（买断制）积分条替换为授权徽标（试用剩余天数/终身），
 *  v0.17.0：点击进入「系统设置」页的授权分区（激活自定价页迁入）。 */
export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const t = useT()
  const user = useSessionStore((s) => s.user)
  const license = useSessionStore((s) => s.license)
  const startOnboarding = useUiStore((s) => s.startOnboarding)

  const balance = user?.credits.balance ?? 0
  const grant = user?.credits.monthly_grant ?? 0
  const barPct = grant > 0 ? Math.min(100, Math.max(4, (balance / grant) * 100)) : 4

  const isLicense = license?.billing_mode === 'license'
  const activated = license?.activated ?? false
  const daysLeft = license?.trial.days_left ?? 0
  const trialPct = activated
    ? 100
    : Math.min(100, Math.max(3, (daysLeft / Math.max(1, license?.trial.days ?? 14)) * 100))
  // ：desktop 形态隐藏作品市场（云社区非本阶段重点；路由侧亦有 MarketGuard 兜底）；
  // v0.17.0：license（买断）形态「定价与积分」换「系统设置」（授权/用量/引擎入口
  // 收口到 /settings，定价页 cloud 存量专用）
  const navGroups = NAV_GROUPS.map((g) => {
    let items = g.items
    if (isLicense) {
      items = items.filter((i) => i.to !== '/pricing')
      if (g.labelKey === 'app.sidebar.group.account') {
        items = [{ to: '/settings', labelKey: 'app.sidebar.nav.settings' }, ...items]
      }
      if (license?.mode === 'desktop') {
        items = items.filter((i) => i.to !== '/market')
      }
    }
    return { ...g, items }
  })

  return (
    <aside className="sidebar w-[212px] flex-none border-r flex flex-col border-line bg-bg">
      <div className="sidebar-head px-[18px] pt-6 pb-5">
        <div className="flex items-center gap-2 cursor-pointer" onClick={() => navigate('/studio')}>
          <Logo size={22} />
          <div className="sidebar-head-text">
            <div className="text-md font-extrabold tracking-tight leading-none">MELOYU</div>
            <div className="text-2xs mt-1 text-dim">
              {t('app.sidebar.tagline')}
            </div>
          </div>
        </div>
      </div>
      <nav className="rule-t pt-3 flex-1 overflow-y-auto">
        {navGroups.map((group) => (
          <div key={group.labelKey}>
            <div className="label px-[18px] pt-5 pb-2">{t(group.labelKey)}</div>
            {group.items.map((item) => {
              const on =
                item.to === '/library'
                  ? location.pathname.startsWith('/library') || location.pathname.startsWith('/works')
                  : location.pathname === item.to
              return (
                <button
                  type="button"
                  key={item.to}
                  className={`nav-item ${on ? 'on' : ''}`}
                  onClick={() => navigate(item.to)}
                >
                  <span className="dot"></span>
                  {t(item.labelKey)}
                  {item.kbd && <span className="kbd">{item.kbd}</span>}
                </button>
              )
            })}
          </div>
        ))}
      </nav>
      {/* pb 预留底部固定播放器(68px)的遮挡带，保证积分区与账号菜单可点击 */}
      <div className="sidebar-bottom rule-t px-[18px] pt-[18px] pb-[84px]">
        <button className="btn btn-ghost w-full btn-sm mb-3" onClick={startOnboarding}>
          {t('app.sidebar.onboarding')}
        </button>
        {/* 积分/授权信息块：≤1024 折叠态由 .sidebar-credits 隐藏（48px 放不下数字） */}
        {isLicense ? (
          /* license 模式：授权徽标（试用剩余 / 终身 / 已到期），点击进系统设置的授权分区 */
          <button className="sidebar-credits block w-full text-left" onClick={() => navigate('/settings')}>
            <div className="flex items-center justify-between">
              <span className="label">{t('license.sidebar.label')}</span>
              <span className="text-xs font-bold num text-acc">
                {activated
                  ? t('license.sidebar.lifetime')
                  : daysLeft > 0
                    ? `${daysLeft}${t('license.sidebar.daysUnit')}`
                    : t('license.sidebar.expired')}
              </span>
            </div>
            <div className="h-[3px] mt-2 bg-bg-3">
              <div
                className={daysLeft > 0 || activated ? 'h-full bg-acc' : 'h-full bg-bad'}
                style={{ width: `${trialPct}%` }}
              ></div>
            </div>
          </button>
        ) : (
          <div className="sidebar-credits">
            <div className="flex items-center justify-between">
              <span className="label">{t('app.sidebar.credits')}</span>
              <span className="text-xs font-bold num text-acc">
                {formatNum(balance)}
              </span>
            </div>
            <div className="h-[3px] mt-2 bg-bg-3">
              <div className="h-full bg-acc" style={{ width: `${barPct}%` }}></div>
            </div>
          </div>
        )}
        {/* 账号管理区：档位行 + 弹出菜单（改密/导出/登出全部/删号/登出） */}
        <AccountMenu />
        {/* up：菜单向上展开，避开下方固定播放器遮挡带 */}
        <div className="mt-3 flex sidebar-lang">
          <LangSwitch up />
        </div>
      </div>
    </aside>
  )
}
