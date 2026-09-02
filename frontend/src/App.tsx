import { HashRouter, Navigate, Route, Routes, Outlet, useLocation } from 'react-router-dom'
import { useEffect, useRef } from 'react'
import Sidebar from './components/layout/Sidebar'
import TransportBar from './components/layout/TransportBar'
import Onboarding from './components/layout/Onboarding'
import ToastHost from './components/common/ToastHost'
import ConfirmDialog from './components/common/ConfirmDialog'
import LoginView from './views/LoginView'
import LandingView from './views/LandingView'
import StudioView from './views/StudioView'
import LyricsView from './views/LyricsView'
import LibraryView from './views/LibraryView'
import WorkDetailView from './views/WorkDetailView'
import RightsView from './views/RightsView'
import PricingView from './views/PricingView'
import ModelCenterView from './views/ModelCenterView'
import ComingSoonView from './views/ComingSoonView'
import { useSessionStore } from './stores/session'
import { useMetaStore } from './stores/meta'
import { useUiStore, hasOnboarded } from './stores/ui'
import { usePlayerStore } from './stores/player'
import { getToken } from './lib/token'
import { useT, useI18nStore } from './i18n'

/** 快捷键：1-8 切换视图；空格 播放/暂停（输入控件内不触发，复刻原型行为） */
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
}

function AppLayout() {
  const location = useLocation()
  const t = useT()
  const { user, ready, bootstrap } = useSessionStore()
  const loadMeta = useMetaStore((s) => s.load)
  const reloadMeta = useMetaStore((s) => s.reloadForLocale)
  const startOnboarding = useUiStore((s) => s.startOnboarding)

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

  // 首次登录后自动开启新手引导（600ms，复刻原型）
  useEffect(() => {
    if (!ready || !user) return
    if (!hasOnboarded()) {
      const t = window.setTimeout(() => startOnboarding(), 600)
      return () => window.clearTimeout(t)
    }
  }, [ready, user, startOnboarding])

  if (!user && !ready) {
    return (
      <div className="h-full flex items-center justify-center" style={{ background: 'var(--bg)' }}>
        <span className="label">{t('app.loading')}</span>
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
      <ShortcutHandler />
    </div>
  )
}

function ShortcutHandler() {
  const toggle = usePlayerStore((s) => s.toggle)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
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

function RootRoutes() {
  const hasToken = useSessionStore((s) => s.user !== null) || Boolean(getToken())
  return (
    <Routes>
      {/* 产品落地页：对外展示入口。未登录访问 / 直接落地；已登录直达工作台。 /landing 恒定可访问（演示/分享）。 */}
      <Route path="/landing" element={<LandingView />} />
      <Route path="/" element={hasToken ? <Navigate to="/studio" replace /> : <LandingView />} />
      <Route path="/login" element={<LoginGuard />} />
      {hasToken ? (
        <Route element={<AppLayout />}>
          <Route path="/studio" element={<StudioView />} />
          <Route path="/lyrics" element={<LyricsView />} />
          <Route path="/arrange" element={<ComingSoonView kind="arrange" />} />
          <Route path="/edit" element={<ComingSoonView kind="edit" />} />
          <Route path="/pitch" element={<ComingSoonView kind="pitch" />} />
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
      <RootRoutes />
      <ToastHost />
      <ConfirmDialog />
    </HashRouter>
  )
}
