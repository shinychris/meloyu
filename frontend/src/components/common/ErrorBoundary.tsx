import { Component, type ErrorInfo, type ReactNode } from 'react'
import { useT } from '../../i18n'

/** 崩溃兜底 UI（函数组件：走 useT 订阅语言，切语言即时生效） */
function ErrorFallback({ onReload }: { onReload: () => void }) {
  const t = useT()
  return (
    <div className="h-full flex items-center justify-center" style={{ background: 'var(--bg)' }}>
      <div className="card p-8 w-[380px] text-center pop">
        <div className="text-[17px] font-extrabold tracking-tight">{t('app.error.title')}</div>
        <div className="text-[12px] mt-3 leading-relaxed" style={{ color: 'var(--muted)' }}>
          {t('app.error.desc')}
        </div>
        <button className="btn btn-acc !py-2 !px-5 text-[12px] mt-6" onClick={onReload}>
          {t('app.error.reload')}
        </button>
      </div>
    </div>
  )
}

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

/**
 * 根路由错误边界（自写 class，零新依赖）：任何视图渲染抛错时兜底为
 * 双语「界面出错了 / Something went wrong」+ 重载按钮；原始错误保留在控制台。
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    // 保留原始错误与组件栈，方便排查
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  onReload = (): void => {
    window.location.reload()
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return <ErrorFallback onReload={this.onReload} />
    }
    return this.props.children
  }
}
