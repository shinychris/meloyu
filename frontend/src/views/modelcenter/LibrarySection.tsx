import { useState } from 'react'
import { useModelCenter } from './context'
import { inputCls, fmtSize } from './shared'
import { deleteModel, pullModel } from '../../api/models'
import { useConfirmStore } from '../../stores/confirm'
import { toast } from '../../stores/toast'
import { useT } from '../../i18n'

/**
 * 本地模型库分区（F-FE-09 拆分）：Ollama 本地模型表 + 下载区（含下载进度）。
 * pullTag/pulling 为本区块瞬态；activeOp/refreshAll 在共享 context。
 */
export default function LibrarySection() {
  const t = useT()
  const confirm = useConfirmStore((s) => s.confirm)
  const {
    local, settings, presets,
    setPickedModel, setActiveOp, refreshAll,
    saveBackend, activeOp,
  } = useModelCenter()
  const [pullTag, setPullTag] = useState('')
  const [pulling, setPulling] = useState(false)

  const removeModel = async (name: string) => {
    const ok = await confirm({
      title: t('models.del.title', { name }),
      description: t('models.del.desc'),
      confirmText: t('common.delete'),
      danger: true,
    })
    if (!ok) return
    try {
      const op = await deleteModel(name)
      if (op.status === 'succeeded') toast(t('models.del.done', { name }))
      else toast(op.error_message || t('models.del.failed'), 'warn')
      await refreshAll()
    } catch {
      /* 拦截器已 toast */
    }
  }

  const startPull = async (tag: string) => {
    const model = tag.trim()
    if (!model) {
      toast(t('models.pull.needTag'))
      return
    }
    setPulling(true)
    try {
      const op = await pullModel(model)
      setActiveOp(op)
      setPullTag('')
      toast(t('models.pull.started', { model }))
    } catch {
      /* 拦截器已 toast（重复下载 / 格式错误等） */
    } finally {
      setPulling(false)
    }
  }

  return (
    <section id="mc-library">
      <div className="label mb-3">{t('models.local.title')}</div>
      <div className="card">
        {local && local.models.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="label">
                <th className="text-left px-4 py-2 font-normal">{t('models.local.col.model')}</th>
                <th className="text-left px-4 py-2 font-normal">{t('models.local.col.params')}</th>
                <th className="text-left px-4 py-2 font-normal">{t('models.local.col.size')}</th>
                <th className="text-right px-4 py-2 font-normal">{t('models.local.col.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {local.models.map((m) => (
                <tr key={m.name} className="rule-t">
                  <td className="px-4 py-2.5">
                    <span className="font-bold">{m.name}</span>
                    {settings?.lyrics_backend === 'ollama' && local.selected === m.name && (
                      <span className="badge badge-solid ml-2">
                        {t('models.local.engineInUse')}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-muted">
                    {m.parameter_size || '—'} · {m.quantization || '—'}
                  </td>
                  <td className="px-4 py-2.5 num text-muted">
                    {fmtSize(m.size_bytes)}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      className="btn btn-sm mr-2"
                      disabled={settings?.lyrics_backend === 'ollama' && local.selected === m.name}
                      onClick={() => {
                        setPickedModel(m.name)
                        void saveBackend('ollama', { ollama_model: m.name })
                      }}
                    >
                      {t('models.local.setEngine')}
                    </button>
                    <button
                      className="btn btn-sm"
                      style={{ color: 'var(--bad)' }}
                      onClick={() => void removeModel(m.name)}
                    >
                      {t('common.delete')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="px-4 py-6 text-sm text-dim">
            {local?.error || t('models.local.empty')}
          </div>
        )}
      </div>

      {/* 下载区 */}
      <div className="card mt-3 p-4">
        <div className="label mb-2">{t('models.pull.title')}</div>
        <div className="flex flex-wrap gap-2 mb-3">
          {(local?.recommended || presets?.recommended_models || []).map((r) => (
            <span
              key={r.tag}
              className="chip"
              title={`${r.note} · ${t('models.pull.aboutSize', { size: r.size_mb })}`}
              onClick={() => setPullTag(r.tag)}
            >
              {r.tag} · ≈{r.size_mb}MB
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            className={`flex-1 px-3 py-2 text-sm ${inputCls}`}
            placeholder={t('models.pull.tagPh')}
            value={pullTag}
            onChange={(e) => setPullTag(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void startPull(pullTag)
            }}
          />
          <button className="btn btn-acc" disabled={pulling || !!activeOp} onClick={() => void startPull(pullTag)}>
            {pulling || activeOp ? t('models.pull.downloading') : t('common.download')}
          </button>
        </div>
        <div className="text-2xs mt-2 text-dim">
          {t('models.pull.note')}
        </div>
        {activeOp && (
          <div className="mt-3">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="font-bold">{activeOp.target}</span>
              <span className="num text-acc">
                {activeOp.progress}% · {activeOp.message}
              </span>
            </div>
            <div className="h-[4px] bg-bg-3">
              <div
                className="h-full transition-all bg-acc"
                style={{ width: `${activeOp.progress}%` }}
              />
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
