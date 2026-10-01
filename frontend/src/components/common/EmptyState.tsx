import type { ReactNode } from 'react'

/** 默认空态图标：四竖条波形，中条品牌绿（源自 StudioView 空态范本）。 */
function WaveIcon() {
  return (
    <svg className="mx-auto" width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <rect x="4" y="16" width="4" height="12" fill="var(--color-line)" />
      <rect x="12" y="10" width="4" height="24" fill="var(--color-line)" />
      <rect x="20" y="5" width="4" height="30" fill="var(--color-acc)" />
      <rect x="28" y="12" width="4" height="20" fill="var(--color-line)" />
    </svg>
  )
}

/** 全站统一空态：虚线框 + 波形图标 + 标题 + 提示 + 可选动作；compact 用于侧栏/面板内的小空态。 */
export function EmptyState({ title, hint, actionLabel, onAction, icon, compact, className }: {
  title: ReactNode
  hint?: ReactNode
  actionLabel?: ReactNode
  onAction?: () => void
  icon?: ReactNode
  compact?: boolean
  className?: string
}) {
  return (
    <div className={`border border-dashed border-line ${compact ? 'py-8 px-4' : 'py-16'} text-center ${className ?? ''}`}>
      {icon ?? <WaveIcon />}
      <div className="text-base mt-4 font-semibold text-muted">{title}</div>
      {hint != null && <div className="text-xs mt-2 leading-relaxed text-dim">{hint}</div>}
      {actionLabel != null && onAction && (
        <button className="btn btn-ghost btn-sm mt-4" onClick={onAction}>{actionLabel}</button>
      )}
    </div>
  )
}
