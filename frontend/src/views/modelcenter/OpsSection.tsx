import { useModelCenter } from './context'
import { OP_TYPE_LABEL } from './shared'
import { formatDateTime } from '../../lib/format'
import { useT } from '../../i18n'

/** 操作记录分区（F-FE-09 拆分）：最近模型操作（下载/删除/部署）。 */
export default function OpsSection() {
  const t = useT()
  const { ops } = useModelCenter()

  return (
    <section id="mc-ops" className="mt-10 mb-10 scroll-mt-4">
      <div className="label mb-3">{t('models.ops.title')}</div>
      {ops.length > 0 ? (
        <div className="card p-4">
          {ops.map((op) => (
            <div key={op.id} className="flex items-center gap-3 text-xs py-1">
              <span className="num text-dim">
                {formatDateTime(op.created_at)}
              </span>
              <span className="font-bold">{t(OP_TYPE_LABEL[op.op_type])}</span>
              <span>{op.target}</span>
              <span className={`flex-1 ${
                op.status === 'succeeded' ? 'text-acc' : op.status === 'failed' ? 'text-bad' : 'text-dim'
              }`}>
                {op.status === 'succeeded' ? t('models.ops.succeeded') : op.status === 'failed'
                  ? t('models.ops.failed', { msg: op.error_message || t('models.ops.unknownError') }) : `${op.progress}% ${op.message}`}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="card p-4 text-sm text-dim">
          {t('models.ops.empty')}
        </div>
      )}
    </section>
  )
}
