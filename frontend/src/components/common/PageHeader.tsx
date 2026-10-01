import type { ReactNode } from 'react'

/** 全站统一的视图页头：小标签 + 28px 标题 + 右侧动作区 + 可选下方附加内容（如 StepBar）。 */
export function PageHeader({ label, title, actions, children }: {
  label: ReactNode
  title: ReactNode
  actions?: ReactNode
  children?: ReactNode
}) {
  return (
    <header className="px-8 pt-6 pb-4">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div className="min-w-0">
          <div className="label">{label}</div>
          <h1 className="text-3xl font-extrabold tracking-tight mt-1">{title}</h1>
        </div>
        {actions}
      </div>
      {children}
    </header>
  )
}
