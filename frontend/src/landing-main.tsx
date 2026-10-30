/**
 * 官网营销站独立入口（F7）：portal 托管的落地页单页构建。
 * 构建：npm run build:landing → dist-landing/（portal 以 PORTAL_LANDING_DIR 挂载）。
 * 与 App 构建互不影响——登录/工作台不进此 bundle。
 *
 * F-FE-32 评估结论：保持 HashRouter。依据——营销站由 portal（Starlette）托管：
 * `GET /` 返回 landing.html，静态资源经 `app.mount("/", StaticFiles(dist-landing))`
 * 挂载且未开 `html=True`，BrowserRouter 深链（如 /pricing）会 404，没有 SPA
 * fallback；deploy/nginx.conf 只服务 App 构建（dist/），与营销站不同源。改
 * BrowserRouter 必须动 portal 路由（超出本次 frontend 限定范围且风险高）；
 * 页面内锚点全部走 JS 滚动（LandingNav 不依赖 href="#..."），首页/购买页等
 * 关键入口均为服务端可达的独立路径（/ 与 /buy）。
 */
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import LandingView from './views/LandingView'
import './i18n' // 模块副作用：locale 初始化（默认 en，localStorage 持久化切换）
import './styles/index.css'

const root = document.getElementById('root')
if (root) {
  createRoot(root).render(
    <HashRouter>
      <LandingView site />
    </HashRouter>,
  )
}
