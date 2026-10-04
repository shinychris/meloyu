/**
 * 官网营销站独立入口（F7）：portal 托管的落地页单页构建。
 * 构建：npm run build:landing → dist-landing/（portal 以 PORTAL_LANDING_DIR 挂载）。
 * 与 App 构建互不影响——登录/工作台不进此 bundle。
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
