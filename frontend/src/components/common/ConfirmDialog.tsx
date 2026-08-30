import { useConfirmStore } from '../../stores/confirm'

/** 敏感操作确认对话框（永久删除等） */
export default function ConfirmDialog() {
  const { visible, options, resolve } = useConfirmStore()
  if (!visible || !options) return null
  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center" style={{ background: 'rgba(0,0,0,.72)' }}>
      <div className="card pop w-[380px] p-6" style={{ borderColor: options.danger ? 'var(--bad)' : 'var(--line2)' }}>
        <div className="text-[15px] font-bold">{options.title}</div>
        {options.description && (
          <div className="text-[12px] mt-2 leading-relaxed" style={{ color: 'var(--muted)' }}>
            {options.description}
          </div>
        )}
        <div className="flex gap-2 mt-6 justify-end">
          <button className="btn btn-ghost !py-1.5 !px-4 text-[12px]" onClick={() => resolve(false)}>
            取消
          </button>
          <button
            className={`btn !py-1.5 !px-4 text-[12px] ${options.danger ? '' : 'btn-acc'}`}
            style={options.danger ? { borderColor: 'var(--bad)', color: 'var(--bad)' } : undefined}
            onClick={() => resolve(true)}
          >
            {options.confirmText ?? '确认'}
          </button>
        </div>
      </div>
    </div>
  )
}
