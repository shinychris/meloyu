import { HashRouter, Navigate, Route, Routes, Outlet, useLocation } from 'react-router-dom'
import { Suspense, lazy, useEffect, useRef } from 'react'
import Sidebar from './components/layout/Sidebar'
import TransportBar from './components/layout/TransportBar'
import Onboarding from './components/layout/Onboarding'
import OnboardingAsk from './components/layout/OnboardingAsk'
import ToastHost from './components/common/ToastHost'
import ConfirmDialog from './components/common/ConfirmDialog'
import ErrorBoundary from './components/common/ErrorBoundary'
// 首屏关键路径直接 import：登录页（F7：落地页已迁官网营销站独立构建
// frontend/dist-landing，由 portal 托管，App 内不再携带）
import LoginView from './views/LoginView'
// 其余视图 lazy（代码分割；React.lazy + Suspense，不引入新依赖）
const StudioView = lazy(() => import('./views/StudioView'))
const LyricsView = lazy(() => import('./views/LyricsView'))
const LibraryView = lazy(() => import('./views/LibraryView'))
const WorkDetailView = lazy(() => import('./views/WorkDetailView'))
const RightsView = lazy(() => import('./views/RightsView'))
const PricingView = lazy(() => import('./views/PricingView'))
const ModelCenterView = lazy(() => import('./views/ModelCenterView'))
const ArrangementView = lazy(() => import('./views/ArrangementView'))
const EditView = lazy(() => import('./views/EditView'))
const PitchView = lazy(() => import('./views/PitchView'))
const MarketView = lazy(() => import('./views/MarketView'))
const ResetPasswordView = lazy(() => import('./views/ResetPasswordView'))
import { useSessionStore } from './stores/session'
import { useMetaStore } from './stores/meta'
import { useUiStore, hasOnboardChoice } from './stores/ui'
import { useConfirmStore } from './stores/confirm'
import { useStudioStore } from './stores/studio'
import { usePlayerStore } from './stores/player'
import { getToken } from './lib/token'
import { useT, useI18nStore } from './i18n'

/** 快捷键：0/1-9 切换视图；空格 播放/暂停（输入控件内不触发，复刻原型行为） */
const SHORTCUT_ROUTES: Record<string, string> = {
  '1': '/studio',
  '2': '/lyrics',
  '3': '/arrange',
  '4': '/edit',
  '5': '/pitch',
  '6': '/library',
  '7': '/rights',
  '8': '/pricing',
  '9': '/models',
  '0': '/market',
}

/** 路由级 Suspense 兜底（lazy chunk 加载中） */
function RouteFallback() {
  const t = useT()
  return (
    <div className="h-full flex items-center justify-center bg-bg">
      <span className="label">{t('app.loading')}</span>
    </div>
  )
}

function AppLayout() {
  const location = useLocation()
  const t = useT()
  const { user, ready, offline, bootstrap } = useSessionStore()
  const desktopShell = useSessionStore((s) => s.desktopShell)
  const loadMeta = useMetaStore((s) => s.load)
  const reloadMeta = useMetaStore((s) => s.reloadForLocale)
  const startAsk = useUiStore((s) => s.startAsk)

  const bootedRef = useRef(false)
  useEffect(() => {
    if (bootedRef.current) return
    bootedRef.current = true
    void bootstrap()
    void loadMeta()
  }, [bootstrap, loadMeta])

  // 语言切换后重拉系统元数据（后端按 Accept-Language 返回本地化 label/灵感词条）
  const locale = useI18nStore((s) => s.locale)
  const localeBootedRef = useRef(false)
  useEffect(() => {
    if (!localeBootedRef.current) {
      localeBootedRef.current = true
      return
    }
    void reloadMeta()
  }, [locale, reloadMeta])

  // 仅首次登录弹询问：由用户选择是否开启新手引导（选择结果按用户记录，不再打扰）
  useEffect(() => {
    if (!ready || !user) return
    if (hasOnboardChoice(user.id)) return
    if (useUiStore.getState().onboardingOpen) return
    const t = window.setTimeout(() => startAsk(), 600)
    return () => window.clearTimeout(t)
  }, [ready, user, startAsk])

  // P1-23：工作台表单草稿按用户水合（防误刷新丢失创作内容）
  useEffect(() => {
    if (ready && user) void useStudioStore.getState().hydrateDraft(user.id)
  }, [ready, user?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!user && !ready) {
    return (
      <div className="h-full flex items-center justify-center bg-bg">
        <span className="label">{t('app.loading')}</span>
      </div>
    )
  }
  // P1-25：后端不可达 ≠ 未登录——token 仍在，展示重试而非踢到登录页重输密码
  if (!user && offline) {
    return (
      <div className="h-full flex items-center justify-center bg-bg">
        <div className="card p-8 w-[380px] text-center pop">
          <div className="text-lg font-extrabold tracking-tight">{t('app.offline.title')}</div>
          <div className="text-sm mt-3 leading-relaxed text-muted">
            {t('app.offline.desc')}
          </div>
          <button
            className="btn btn-acc btn-md mt-6"
            onClick={() => {
              useSessionStore.setState({ ready: false, offline: false })
              void bootstrap()
            }}
          >
            {t('app.offline.retry')}
          </button>
        </div>
      </div>
    )
  }
  if (!user) {
    // F3：桌面形态无 user 只能是会话未就绪/瞬态失败（免登录短路总可取回本地档案），
    // 不弹回登录页（桌面登录被 409 拒绝，回去即死锁）
    if (desktopShell) {
      return (
        <div className="h-full flex items-center justify-center bg-bg">
          <span className="label">{t('app.loading')}</span>
        </div>
      )
    }
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 min-w-0 overflow-y-auto pb-[92px]" id="main">
        <Outlet />
      </main>
      <TransportBar />
      <Onboarding />
      <OnboardingAsk />
      <ShortcutHandler />
    </div>
  )
}

function ShortcutHandler() {
  const toggle = usePlayerStore((s) => s.toggle)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // 弹窗（引导/询问/确认框）打开时不切视图，避免视图切走弹窗悬空
      const ui = useUiStore.getState()
      if (ui.onboardingOpen || ui.askOpen) return
      if (useConfirmStore.getState().visible) return
      const target = e.target as HTMLElement | null
      if (
        target &&
        (target.tagName === 'TEXTAREA' ||
          target.tagName === 'INPUT' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        return
      }
      const route = SHORTCUT_ROUTES[e.key]
      if (route) {
        window.location.hash = `#${route}`
        return
      }
      if (e.code === 'Space') {
        e.preventDefault()
        toggle()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [toggle])
  return null
}

/** 登录页守卫：已登录则跳工作台；本地无 token 则同步清空残留会话（401 后避免回跳循环）。
 *  v0.16.0：desktop 形态免登录（本地档案静默鉴权），登录页不再可达。
 *  v0.16.2（F3 修复）：desktop 判定改为 desktopShell（冷启动即可知）或
 *  license.mode（bootstrap 后兜底），不再依赖登录后才拉到的状态。 */
function LoginGuard() {
  const user = useSessionStore((s) => s.user)
  const desktop = useSessionStore((s) => s.desktopShell || s.license?.mode === 'desktop')
  useEffect(() => {
    if (desktop) return
    if (!getToken()) {
      useSessionStore.setState({ user: null, ready: true })
    }
  }, [desktop])
  if (desktop) {
    return <Navigate to="/studio" replace />
  }
  if (user && getToken()) {
    return <Navigate to="/studio" replace />
  }
  return <LoginView />
}

/** 市场守卫（D-6）：desktop 形态隐藏作品市场（云社区非本阶段重点）。 */
function MarketGuard() {
  const desktop = useSessionStore((s) => s.desktopShell || s.license?.mode === 'desktop')
  if (desktop) {
    return <Navigate to="/studio" replace />
  }
  return <MarketView />
}

/** 密码重置守卫：desktop 形态无账号体系（B6），重置页不可达。 */
function ResetPasswordGuard() {
  const desktop = useSessionStore((s) => s.desktopShell || s.license?.mode === 'desktop')
  if (desktop) {
    return <Navigate to="/studio" replace />
  }
  return <ResetPasswordView />
}

/** 编曲路由壳：URL search 变化（工作台再次「送往编曲」）时以 key remount，
 *  ArrangementView 的首装参数逻辑无需感知参数更新 */
function ArrangeRoute() {
  const location = useLocation()
  return <ArrangementView key={location.search} />
}

function RootRoutes() {
  const hasToken = useSessionStore((s) => s.user !== null) || Boolean(getToken())
  // F3 修复（2026-10-16）：桌面形态免 token 进入（bootstrap 拉本地档案）；
  // 探测只跑一次——壳桥同步命中，裸浏览器直连桌面后端由 /system/meta 兜底
  const desktopShell = useSessionStore((s) => s.desktopShell)
  const detectDesktopShell = useSessionStore((s) => s.detectDesktopShell)
  useEffect(() => {
    void detectDesktopShell()
  }, [detectDesktopShell])
  const enterApp = hasToken || desktopShell
  return (
    <Routes>
      {/* F7：落地页已迁官网（portal 托管 dist-landing）；App 内 / 与旧 /landing
          一律按登录态分流（旧外链 → 登录页，不 404） */}
      <Route path="/" element={enterApp ? <Navigate to="/studio" replace /> : <Navigate to="/login" replace />} />
      <Route path="/landing" element={<Navigate to="/" replace />} />
      <Route path="/login" element={<LoginGuard />} />
      {/* 邮件重置密码（Stripe 回跳页已随 v0.16.0 订阅拆除移除） */}
      <Route path="/reset-password" element={<ResetPasswordGuard />} />
      <Route path="/billing/return" element={<Navigate to="/pricing" replace />} />
      {enterApp ? (
        <Route element={<AppLayout />}>
          <Route path="/studio" element={<StudioView />} />
          <Route path="/lyrics" element={<LyricsView />} />
          {/* 编排视图以 URL search（?work=&version=&candidate=）为装载契约：
              参数变化即 remount 重新装载目标，工作台可重复「送往编曲」 */}
          <Route path="/arrange" element={<ArrangeRoute />} />
          <Route path="/market" element={<MarketGuard />} />
          <Route path="/edit" element={<EditView />} />
          <Route path="/pitch" element={<PitchView />} />
          <Route path="/library" element={<LibraryView />} />
          <Route path="/works/:workId" element={<WorkDetailView />} />
          <Route path="/rights" element={<RightsView />} />
          <Route path="/pricing" element={<PricingView />} />
          <Route path="/models" element={<ModelCenterView />} />
          <Route path="*" element={<Navigate to="/studio" replace />} />
        </Route>
      ) : (
        <Route path="*" element={<Navigate to="/" replace />} />
      )}
    </Routes>
  )
}

export default function App() {
  return (
    <HashRouter>
      <ErrorBoundary>
        <Suspense fallback={<RouteFallback />}>
          <RootRoutes />
        </Suspense>
      </ErrorBoundary>
      <ToastHost />
      <ConfirmDialog />
    </HashRouter>
  )
}
