import { HashRouter, Navigate, Route, Routes, Outlet, useLocation } from 'react-router-dom'
import { Suspense, lazy, useEffect, useRef } from 'react'
import Sidebar from './components/layout/Sidebar'
import TransportBar from './components/layout/TransportBar'
import Onboarding from './components/layout/Onboarding'
import OnboardingAsk from './components/layout/OnboardingAsk'
import ToastHost from './components/common/ToastHost'
import ConfirmDialog from './components/common/ConfirmDialog'
import ErrorBoundary from './components/common/ErrorBoundary'
// 首屏关键路径直接 import：落地页与登录页
import LoginView from './views/LoginView'
import LandingView from './views/LandingView'
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
const BillingReturnView = lazy(() => import('./views/BillingReturnView'))
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
    <div className="h-full flex items-center justify-center" style={{ background: 'var(--bg)' }}>
      <span className="label">{t('app.loading')}</span>
    </div>
  )
}

function AppLayout() {
  const location = useLocation()
  const t = useT()
  const { user, ready, offline, bootstrap } = useSessionStore()
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
      <div className="h-full flex items-center justify-center" style={{ background: 'var(--bg)' }}>
        <span className="label">{t('app.loading')}</span>
      </div>
    )
  }
  // P1-25：后端不可达 ≠ 未登录——token 仍在，展示重试而非踢到登录页重输密码
  if (!user && offline) {
    return (
      <div className="h-full flex items-center justify-center" style={{ background: 'var(--bg)' }}>
        <div className="card p-8 w-[380px] text-center pop">
          <div className="text-[17px] font-extrabold tracking-tight">{t('app.offline.title')}</div>
          <div className="text-[12px] mt-3 leading-relaxed" style={{ color: 'var(--muted)' }}>
            {t('app.offline.desc')}
          </div>
          <button
            className="btn btn-acc !py-2 !px-5 text-[12px] mt-6"
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

/** 登录页守卫：已登录则跳工作台；本地无 token 则同步清空残留会话（401 后避免回跳循环） */
function LoginGuard() {
  const user = useSessionStore((s) => s.user)
  useEffect(() => {
    if (!getToken()) {
      useSessionStore.setState({ user: null, ready: true })
    }
  }, [])
  if (user && getToken()) {
    return <Navigate to="/studio" replace />
  }
  return <LoginView />
}

/** 编曲路由壳：URL search 变化（工作台再次「送往编曲」）时以 key remount，
 *  ArrangementView 的首装参数逻辑无需感知参数更新 */
function ArrangeRoute() {
  const location = useLocation()
  return <ArrangementView key={location.search} />
}

function RootRoutes() {
  const hasToken = useSessionStore((s) => s.user !== null) || Boolean(getToken())
  return (
    <Routes>
      {/* 产品落地页：对外展示入口。未登录访问 / 直接落地；已登录直达工作台。 /landing 恒定可访问（演示/分享）。 */}
      <Route path="/landing" element={<LandingView />} />
      <Route path="/" element={hasToken ? <Navigate to="/studio" replace /> : <LandingView />} />
      <Route path="/login" element={<LoginGuard />} />
      {/* v0.7.0 商业化：Stripe 支付回跳（独立于工作台壳，登录与否都可看）与邮件重置密码 */}
      <Route path="/billing/return" element={<BillingReturnView />} />
      <Route path="/reset-password" element={<ResetPasswordView />} />
      {hasToken ? (
        <Route element={<AppLayout />}>
          <Route path="/studio" element={<StudioView />} />
          <Route path="/lyrics" element={<LyricsView />} />
          {/* 编曲视图以 URL search（?work=&version=&candidate=）为装载契约：
              参数变化即 remount 重新装载目标，工作台可重复「送往编曲」 */}
          <Route path="/arrange" element={<ArrangeRoute />} />
          <Route path="/market" element={<MarketView />} />
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
