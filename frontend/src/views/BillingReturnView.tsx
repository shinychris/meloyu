import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useSessionStore } from '../stores/session'
import { toast } from '../stores/toast'
import { useT } from '../i18n'
import LangSwitch from '../components/common/LangSwitch'

/**
 * 支付回跳页（#/billing/return?status=success|cancel&session_id=…）。
 * Stripe 付完/取消后整页跳回。success：说明 webhook 异步激活（几秒到账），
 * 提供「刷新状态」（调 /auth/me 更新用户 store）与回定价页/工作台链接；
 * cancel：已取消提示。独立于 AppLayout（无侧栏），风格同 LoginView。
 */
export default function BillingReturnView() {
  const t = useT()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  // 仅 success 有专属文案；cancel / 未知 status 一律按已取消展示
  const success = params.get('status') === 'success'
  const sessionId = params.get('session_id')
  const refreshUser = useSessionStore((s) => s.refreshUser)
  const [refreshing, setRefreshing] = useState(false)
  /** 自动确认中（P2-20）：webhook 几秒到账，替用户盯着，付费转化最敏感的时刻 */
  const [autoChecking, setAutoChecking] = useState(success)
  const baselinePlanRef = useRef<string | null>(null)

  useEffect(() => {
    if (!success) return
    let stopped = false
    const poll = async (attempt: number) => {
      if (stopped || attempt > 10) {
        if (!stopped) setAutoChecking(false)
        return
      }
      try {
        await refreshUser()
        const plan = useSessionStore.getState().user?.plan ?? null
        if (baselinePlanRef.current == null) {
          baselinePlanRef.current = plan
        } else if (plan !== baselinePlanRef.current) {
          stopped = true
          setAutoChecking(false)
          toast(t('billing.return.planActive'))
          navigate('/studio')
          return
        }
      } catch {
        /* 网络抖动继续下一轮 */
      }
      window.setTimeout(() => void poll(attempt + 1), 3000)
    }
    void poll(1)
    return () => {
      stopped = true
    }
  }, [success, refreshUser, navigate, t])

  const onRefresh = async () => {
    if (refreshing) return
    setRefreshing(true)
    try {
      await refreshUser()
      toast(t('billing.return.refreshed'))
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="login-bg h-screen flex items-center justify-center overflow-hidden">
      <div className="absolute top-4 right-4 z-10">
        <LangSwitch />
      </div>
      <div className="w-[420px] pop">
        <div className="card p-7">
          <div className="flex items-center gap-2.5 mb-5">
            <span
              className="dot"
              style={{
                width: 8,
                height: 8,
                background: success ? 'var(--acc)' : 'var(--warn)',
              }}
            ></span>
            <div className="label">{t('billing.return.label')}</div>
          </div>

          {success ? (
            <>
              <div className="text-xl font-extrabold tracking-tight">{t('billing.return.successTitle')}</div>
              <div className="text-sm mt-3 leading-relaxed text-muted">
                {t('billing.return.successDesc')}
              </div>
              <div className="text-xs mt-2 leading-relaxed text-dim">
                {t('billing.return.refreshHint')}
              </div>
              {sessionId && (
                <div className="text-2xs num mt-3 truncate text-dim" title={sessionId}>
                  session: {sessionId}
                </div>
              )}
              <div className="flex gap-2 mt-6">
                <button
                  className="btn btn-acc btn-md flex-1"
                  disabled={refreshing || autoChecking}
                  onClick={() => void onRefresh()}
                >
                  {autoChecking
                    ? t('billing.return.autoChecking')
                    : refreshing
                      ? t('billing.return.refreshing')
                      : t('billing.return.refresh')}
                </button>
              </div>
            </>
          ) : (
            // cancel / 未知 status：按已取消展示（不产生扣款）
            <>
              <div className="text-xl font-extrabold tracking-tight">{t('billing.return.cancelTitle')}</div>
              <div className="text-sm mt-3 leading-relaxed text-muted">
                {t('billing.return.cancelDesc')}
              </div>
            </>
          )}

          <div className="mt-6 pt-4 rule-t flex items-center gap-4 text-sm">
            <Link to="/pricing" className="font-bold text-acc">
              {t('billing.return.backPricing')}
            </Link>
            <Link to="/studio" className="font-bold text-muted">
              {t('billing.return.backStudio')}
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
