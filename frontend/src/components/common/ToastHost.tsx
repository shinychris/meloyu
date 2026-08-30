import { useToastStore } from '../../stores/toast'

/** 全局 toast 容器（定位与动画对齐原型 .toast，从下弹出） */
export default function ToastHost() {
  const toasts = useToastStore((s) => s.toasts)
  if (toasts.length === 0) return null
  return (
    <div className="toast-stack">
      {toasts.map((t) => (
        <div key={t.id} className={`toast-item ${t.kind === 'info' ? '' : t.kind}`}>
          {t.message}
        </div>
      ))}
    </div>
  )
}
