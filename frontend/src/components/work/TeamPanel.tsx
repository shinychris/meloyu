import type { TeamSpaceInfo } from '../../types/api'
import { addMember, changeMemberRole, createSpace, removeMember } from '../../api/team'
import { toast } from '../../stores/toast'
import { useT } from '../../i18n'
import { useState } from 'react'

/**
 * 团队空间面板（FR-13）：共享作品的成员与角色管理（所有者操作）。
 * 角色：editor 编辑 / commenter 评论 / viewer 查看（owner 不可降级）。
 */
export default function TeamPanel({ space, onChanged }: { space: TeamSpaceInfo; onChanged: () => void }) {
  const t = useT()
  const [emailDraft, setEmailDraft] = useState('')
  const [role, setRole] = useState('commenter')
  const [busy, setBusy] = useState(false)

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

  const onRemove = async (userId: string) => {
    try {
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

  const onCreateSpace = async () => {
    const name = window.prompt(t('team.prompt.spaceName') ?? '')
    if (!name || !name.trim()) return
    try {
      await createSpace(name.trim())
      toast(t('team.toast.spaceCreated'))
      onChanged()
    } catch {
      /* 拦截器已 toast */
    }
  }

  return (
    <div className="card p-3" data-testid="team-panel">
      <div className="flex items-center justify-between">
        <div className="label">{t('team.title')}</div>
        <span className="text-[9px] px-1.5 py-0.5" style={{ background: 'var(--bg3)', color: 'var(--muted)' }}>
          {space.name}
        </span>
      </div>

      <div className="mt-2 space-y-1">
        {space.members.map((m) => (
          <div key={m.user_id} className="flex items-center gap-1.5 text-[10px]">
            <span className="w-16 truncate" style={{ color: 'var(--muted)' }}>
              {m.user_id.slice(0, 8)}…
            </span>
            {m.role === 'owner' ? (
              <span className="text-[9px] font-bold px-1" style={{ color: 'var(--acc)' }}>
                {t('team.role.owner')}
              </span>
            ) : (
              <select
                className="!text-[10px] !py-0.5 flex-1"
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
            className="!text-[10px] flex-1"
            placeholder={t('team.emailPlaceholder')}
            value={emailDraft}
            maxLength={120}
            onChange={(e) => setEmailDraft(e.target.value)}
          />
          <select className="!text-[10px] !py-0.5" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="editor">{t('team.role.editor')}</option>
            <option value="commenter">{t('team.role.commenter')}</option>
            <option value="viewer">{t('team.role.viewer')}</option>
          </select>
          <button className="btn btn-ghost !py-1 !px-2 text-[10px]" disabled={busy} onClick={() => void onAdd()}>
            {t('team.addMember')}
          </button>
        </div>
      )}

      <div className="flex gap-2 mt-2">
        <button className="btn btn-ghost w-full !py-1 text-[10px]" onClick={() => void onCreateSpace()}>
          {t('team.createSpace')}
        </button>
      </div>
      <div className="text-[9px] mt-1.5 leading-relaxed" style={{ color: 'var(--dim)' }}>
        {t('team.roleHint')}
      </div>
    </div>
  )
}
