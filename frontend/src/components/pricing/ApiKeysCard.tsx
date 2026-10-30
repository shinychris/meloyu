import { useEffect, useState } from 'react'
import type { ApiKeyInfo } from '../../types/api'
import { createApiKey, listApiKeys, revokeApiKey } from '../../api/apiKeys'
import { confirmDialog } from '../../stores/confirm'
import { toast } from '../../stores/toast'
import { useT } from '../../i18n'

/** 开放 API 密钥卡（FR-19，v0.8.2）：签发（完整 key 仅一次）/列表/吊销 */
export default function ApiKeysCard() {
  const t = useT()
  const [keys, setKeys] = useState<ApiKeyInfo[]>([])
  const [nameDraft, setNameDraft] = useState('')
  const [freshKey, setFreshKey] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = () => {
    listApiKeys()
      .then((r) => setKeys(r.items))
      .catch(() => {})
  }
  useEffect(refresh, [])

  const issue = async () => {
    if (busy) return
    const name = nameDraft.trim()
    if (!name) {
      toast(t('apikey.toast.nameRequired'), 'warn')
      return
    }
    setBusy(true)
    try {
      const k = await createApiKey(name)
      setFreshKey(k.key)
      setNameDraft('')
      refresh()
    } catch {
      /* 拦截器已 toast（上限 5 个等） */
    } finally {
      setBusy(false)
    }
  }

  const revoke = async (id: string, name: string) => {
    // F-FE-22：吊销密钥为破坏性操作（使用该 key 的集成立即失效），二次确认
    const ok = await confirmDialog({
      title: t('apikey.confirm.revokeTitle', { name }),
      description: t('apikey.confirm.revokeDesc'),
      confirmText: t('apikey.revoke'),
      danger: true,
    })
    if (!ok) return
    try {
      await revokeApiKey(id)
      refresh()
    } catch {
      /* 拦截器已 toast */
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(freshKey)
      toast(t('common.copied'))
    } catch {
      /* 剪贴板不可用则手动复制 */
    }
  }

  return (
    <div className="rule-t px-8 py-4" data-testid="apikeys-card">
      <div className="label mb-2">{t('apikey.title')}</div>
      <div className="text-2xs leading-relaxed text-dim" style={{ maxWidth: 720 }}>
        {t('apikey.hint')}
      </div>

      {freshKey && (
        <div className="card p-3 mt-3" style={{ borderColor: 'var(--acc)' }}>
          <div className="text-2xs font-bold text-acc">{t('apikey.freshNotice')}</div>
          <div className="flex gap-2 mt-1.5 items-center">
            <code className="text-xs flex-1 break-all text-txt">{freshKey}</code>
            <button className="btn btn-ghost btn-sm" onClick={() => void copy()}>
              {t('common.copy')}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setFreshKey('')}>
              {t('common.close')}
            </button>
          </div>
        </div>
      )}

      <div className="flex gap-2 mt-3 max-w-[560px]">
        <input
          type="text"
          className="!text-xs flex-1"
          maxLength={60}
          placeholder={t('apikey.namePlaceholder')}
          value={nameDraft}
          onChange={(e) => setNameDraft(e.target.value)}
        />
        <button className="btn btn-acc btn-sm" disabled={busy} onClick={() => void issue()}>
          {t('apikey.issue')}
        </button>
      </div>

      <div className="mt-3 tx-rows max-w-[720px]">
        {keys.length === 0 ? (
          <div className="py-4 text-xs text-dim">{t('apikey.empty')}</div>
        ) : (
          keys.map((k) => (
            <div key={k.id} className="row !cursor-default" style={{ gridTemplateColumns: '140px 160px 150px 80px' }}>
              <span className="text-xs truncate text-muted">{k.name}</span>
              <code className="text-2xs text-dim">{k.prefix}…</code>
              <span className="text-2xs num text-dim">
                {k.last_used_at ? k.last_used_at.slice(0, 16).replace('T', ' ') : '—'}
              </span>
              <button className="btn btn-ghost !py-0.5 !px-2 text-2xs justify-self-end" onClick={() => void revoke(k.id, k.name)}>
                {t('apikey.revoke')}
              </button>
            </div>
          ))
        )}
      </div>
      <div className="text-2xs mt-2 leading-relaxed text-dim" style={{ maxWidth: 720 }}>
        {t('apikey.endpointHint')}
      </div>
    </div>
  )
}
