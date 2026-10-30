import type { TeamSpaceInfo } from '../../types/api'
import { addMember, changeMemberRole, createSpace, removeMember } from '../../api/team'
import { toast } from '../../stores/toast'
import { useT } from '../../i18n'
import { useEffect, useRef, useState } from 'react'

/**
 * 团队空间面板（FR-13）：共享作品的成员与角色管理（所有者操作）。
 * 角色：editor 编辑 / commenter 评论 / viewer 查看（owner 不可降级）。
 */

/** 新建空间弹窗（F-FE-21：替代 window.prompt，与全站 modal 体系一致；
 *  Enter 提交 / Esc 取消 / 打开即聚焦输入框） */
function CreateSpaceModal({ onClose, onCreate }: {
  onClose: () => void
  onCreate: (name: string) => void
}) {
  const t = useT()
  const [name, setName] = useState('')
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    onCreate(trimmed)
  }

  return (
    <div className="modal-overlay">
      <div className="card pop w-[380px] p-6">
        <div className="text-md font-bold">{t('team.modal.createTitle')}</div>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <div>
            <div className="text-2xs mb-1 text-dim">{t('team.prompt.spaceName')}</div>
            <input
              ref={inputRef}
              type="text"
              value={name}
              maxLength={60}
              placeholder={t('team.prompt.spaceName')}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') onClose()
              }}
            />
          </div>
          <div className="flex gap-2 justify-end pt-1">
            <button type="button" className="btn btn-ghost btn-md" onClick={onClose}>
              {t('common.cancel')}
            </button>
            <button type="submit" className="btn btn-acc btn-md" disabled={!name.trim()}>
              {t('team.modal.create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function TeamPanel({ space, onChanged }: { space: TeamSpaceInfo; onChanged: () => void }) {
  const t = useT()
  const [emailDraft, setEmailDraft] = useState('')
  const [role, setRole] = useState('commenter')
  const [busy, setBusy] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)

  const onCreateSpace = async (name: string) => {
    setCreateOpen(false)
    try {
      await createSpace(name)
      toast(t('team.toast.spaceCreated'))
      onChanged()
    } catch {
      /* 拦截器已 toast */
    }
  }

  const onAdd = async () => {
    if (busy) return
    const email = emailDraft.trim()
    if (!email) {
      toast(t('team.toast.emailRequired'), 'warn')
      return
    }
    setBusy(true)
    try {
      await addMember(space.id, email, role)
      setEmailDraft('')
      toast(t('team.toast.memberAdded'))
      onChanged()
    } catch {
      /* 拦截器已 toast（未注册邮箱/已是成员） */
    } finally {
      setBusy(false)
    }
  }

  const onRemove = async (userId: string) => {    try {
      await removeMember(space.id, userId)
      onChanged()
    } catch {
      /* 拦截器已 toast */
    }
  }

  const onRole = async (userId: string, r: string) => {
    try {
      await changeMemberRole(space.id, userId, r)
      onChanged()
    } catch {
      /* 拦截器已 toast */
    }
  }

  return (
    <div className="card p-3" data-testid="team-panel">
      <div className="flex items-center justify-between">
        <div className="label">{t('team.title')}</div>
        <span className="badge">{space.name}</span>
      </div>

      <div className="mt-2 space-y-1">
        {space.members.map((m) => (
          <div key={m.user_id} className="flex items-center gap-1.5 text-2xs">
            <span className="w-16 truncate text-muted">
              {m.user_id.slice(0, 8)}…
            </span>
            {m.role === 'owner' ? (
              <span className="text-2xs font-bold px-1 text-acc">
                {t('team.role.owner')}
              </span>
            ) : (
              <select
                className="!text-2xs !py-0.5 flex-1"
                value={m.role}
                disabled={!space.is_owner}
                onChange={(e) => void onRole(m.user_id, e.target.value)}
              >
                <option value="editor">{t('team.role.editor')}</option>
                <option value="commenter">{t('team.role.commenter')}</option>
                <option value="viewer">{t('team.role.viewer')}</option>
              </select>
            )}
            {space.is_owner && m.role !== 'owner' && (
              <button className="iconbtn" title={t('team.removeMember')} onClick={() => void onRemove(m.user_id)}>
                <svg viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.4" fill="none">
                  <path d="M3 4h10M6 4V2.5h4V4M5 4l.7 9h4.6l.7-9" />
                </svg>
              </button>
            )}
          </div>
        ))}
      </div>

      {space.is_owner && (
        <div className="flex gap-1.5 mt-2">
          <input
            type="text"
            className="!text-2xs flex-1"
            placeholder={t('team.emailPlaceholder')}
            value={emailDraft}
            maxLength={120}
            onChange={(e) => setEmailDraft(e.target.value)}
          />
          <select className="!text-2xs !py-0.5" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="editor">{t('team.role.editor')}</option>
            <option value="commenter">{t('team.role.commenter')}</option>
            <option value="viewer">{t('team.role.viewer')}</option>
          </select>
          <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void onAdd()}>
            {t('team.addMember')}
          </button>
        </div>
      )}

      <div className="flex gap-2 mt-2">
        <button className="btn btn-ghost w-full btn-sm" onClick={() => setCreateOpen(true)}>
          {t('team.createSpace')}
        </button>
      </div>
      <div className="text-2xs mt-1.5 leading-relaxed text-dim">
        {t('team.roleHint')}
      </div>
      {createOpen && (
        <CreateSpaceModal onClose={() => setCreateOpen(false)} onCreate={(name) => void onCreateSpace(name)} />
      )}
    </div>
  )
}
