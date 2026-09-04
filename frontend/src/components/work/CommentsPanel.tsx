import { useCallback, useEffect, useState } from 'react'
import type { WorkCommentItem } from '../../types/api'
import { apiDelete, apiGet, apiPatch, apiPost } from '../../api/client'
import { usePlayerStore } from '../../stores/player'
import { toast } from '../../stores/toast'
import { useT } from '../../i18n'
import { formatDuration } from '../../lib/format'

function listComments(workId: string): Promise<{ items: WorkCommentItem[]; total: number }> {
  return apiGet(`/works/${workId}/comments`)
}

/**
 * 协作评论面板（FR-13）：评论锚定作品时间轴——发评时默认取播放器当前时间，
 * 点击锚点跳转播放定位；可标记 resolved / 删除（按角色与作者判定，服务端校验）。
 */
export default function CommentsPanel({ workId, canComment }: { workId: string; canComment: boolean }) {
  const t = useT()
  const [items, setItems] = useState<WorkCommentItem[]>([])
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const position = usePlayerStore((s) => s.position)
  const seekTo = usePlayerStore((s) => s.seekTo)
  const current = usePlayerStore((s) => s.current)

  const refresh = useCallback(() => {
    listComments(workId)
      .then((r) => setItems(r.items))
      .catch(() => {})
  }, [workId])
  useEffect(refresh, [refresh])

  const submit = async () => {
    if (busy) return
    const text = body.trim()
    if (!text) {
      toast(t('comments.toast.empty'), 'warn')
      return
    }
    setBusy(true)
    try {
      await apiPost(`/works/${workId}/comments`, {
        time_sec: Math.round(position * 10) / 10,
        body: text,
      })
      setBody('')
      refresh()
    } catch {
      /* 拦截器已 toast（viewer 40301 / 锚点超界 40001） */
    } finally {
      setBusy(false)
    }
  }

  const jump = (sec: number) => {
    if (current) {
      seekTo(sec)
    } else {
      toast(t('comments.toast.playFirst'))
    }
  }

  const onResolve = async (c: WorkCommentItem) => {
    try {
      await apiPatch(`/comments/${c.id}`, { resolved: !c.resolved })
      refresh()
    } catch {
      /* 拦截器已 toast */
    }
  }

  const onDelete = async (c: WorkCommentItem) => {
    try {
      await apiDelete(`/comments/${c.id}`)
      refresh()
    } catch {
      /* 拦截器已 toast */
    }
  }

  return (
    <div className="card p-3" data-testid="comments-panel">
      <div className="flex items-center justify-between">
        <div className="label">{t('comments.title')}</div>
        <span className="text-[9px]" style={{ color: 'var(--dim)' }}>
          {t('comments.count', { n: items.length })}
        </span>
      </div>

      {canComment && (
        <div className="mt-2">
          <textarea
            rows={2}
            className="!text-[11px]"
            maxLength={1000}
            placeholder={t('comments.placeholder', { time: formatDuration(position) })}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <div className="flex items-center justify-between mt-1">
            <span className="text-[9px]" style={{ color: 'var(--dim)' }}>
              {t('comments.anchorHint', { time: formatDuration(position) })}
            </span>
            <button className="btn btn-acc !py-1 !px-2.5 text-[10px]" disabled={busy} onClick={() => void submit()}>
              {t('comments.submit')}
            </button>
          </div>
        </div>
      )}

      <div className="mt-2 space-y-1.5 max-h-64 overflow-y-auto">
        {items.length === 0 ? (
          <div className="text-[10px] py-3 text-center" style={{ color: 'var(--dim)' }}>
            {t('comments.empty')}
          </div>
        ) : (
          items.map((c) => (
            <div
              key={c.id}
              className="flex items-start gap-2 px-2 py-1.5"
              style={{ background: 'var(--bg2)', opacity: c.resolved ? 0.5 : 1 }}
            >
              <button
                className="text-[9px] px-1.5 py-0.5 font-bold num shrink-0"
                style={{ background: 'var(--acc-dim)', color: 'var(--acc)' }}
                title={t('comments.jump')}
                onClick={() => jump(c.time_sec)}
              >
                {formatDuration(c.time_sec)}
              </button>
              <div className="min-w-0 flex-1">
                <div className="text-[10px]" style={{ color: 'var(--muted)', wordBreak: 'break-word' }}>
                  {c.body}
                </div>
                <div className="text-[9px] mt-0.5" style={{ color: 'var(--dim)' }}>
                  {c.author_nickname} · {c.created_at.slice(0, 16).replace('T', ' ')}
                </div>
              </div>
              {canComment && (
                <div className="flex gap-1 shrink-0">
                  <button className="iconbtn" title={t('comments.resolve')} onClick={() => void onResolve(c)}>
                    <svg viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.6" fill="none">
                      <path d="M2.5 8.5l3.5 3.5 7-8" />
                    </svg>
                  </button>
                  <button className="iconbtn" title={t('common.delete')} onClick={() => void onDelete(c)}>
                    <svg viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.4" fill="none">
                      <path d="M3 4h10M6 4V2.5h4V4M5 4l.7 9h4.6l.7-9" />
                    </svg>
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
