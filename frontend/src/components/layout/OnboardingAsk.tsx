import { useSessionStore } from '../../stores/session'
import { useUiStore, markOnboardChoice } from '../../stores/ui'
import { useT } from '../../i18n'

/** 首次登录询问弹窗：让用户选择是否开启新手引导（选择一次后不再出现） */
export default function OnboardingAsk() {
  const t = useT()
  const user = useSessionStore((s) => s.user)
  const { askOpen, resolveAsk } = useUiStore()
  if (!askOpen || !user) return null
  // 点遮罩等同「暂不」：同样记录选择，避免下次登录再次打扰
  const choose = (start: boolean) => {
    markOnboardChoice(user.id)
    resolveAsk(start)
  }
  return (
    <div
      className="fixed inset-0 z-[95] flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,.72)' }}
      onClick={() => choose(false)}
      role="dialog"
      aria-modal="true"
      aria-label={t('layout.ob.askTitle')}
      onKeyDown={(e) => {
        if (e.key === 'Escape') choose(false)
      }}
      tabIndex={-1}
    >
      <div
        className="card pop w-[380px] p-6"
        style={{ borderColor: 'var(--line2)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-[15px] font-bold">{t('layout.ob.askTitle')}</div>
        <div className="text-[12px] mt-2 leading-relaxed" style={{ color: 'var(--muted)' }}>
          {t('layout.ob.askDesc')}
        </div>
        <div className="flex gap-2 mt-6 justify-end">
          <button className="btn btn-ghost !py-1.5 !px-4 text-[12px]" onClick={() => choose(false)}>
            {t('layout.ob.askSkip')}
          </button>
          <button className="btn btn-acc !py-1.5 !px-4 text-[12px] font-bold" onClick={() => choose(true)}>
            {t('layout.ob.askStart')}
          </button>
        </div>
      </div>
    </div>
  )
}
