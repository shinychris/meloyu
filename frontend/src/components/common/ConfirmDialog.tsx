import { useConfirmStore } from '../../stores/confirm'
import { useT } from '../../i18n'

/** 敏感操作确认对话框（永久删除等） */
export default function ConfirmDialog() {
  const t = useT()
  const { visible, options, resolve } = useConfirmStore()
  if (!visible || !options) return null
  return (
    <div className="modal-overlay">
      <div className="card pop w-[380px] p-6" style={{ borderColor: options.danger ? 'var(--bad)' : 'var(--line2)' }}>
        <div className="text-md font-bold">{options.title}</div>
        {options.description && (
          <div className="text-sm mt-2 leading-relaxed text-muted">
            {options.description}
          </div>
        )}
        <div className="flex gap-2 mt-6 justify-end">
          <button className="btn btn-ghost btn-md" onClick={() => resolve(false)}>
            {t('common.cancel')}
          </button>
          <button
            className={`btn btn-md ${options.danger ? '' : 'btn-acc'}`}
            style={options.danger ? { borderColor: 'var(--bad)', color: 'var(--bad)' } : undefined}
            onClick={() => resolve(true)}
          >
            {options.confirmText ?? t('common.confirm')}
          </button>
        </div>
      </div>
    </div>
  )
}
