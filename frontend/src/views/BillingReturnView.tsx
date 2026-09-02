import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
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
  const [params] = useSearchParams()
  // 仅 success 有专属文案；cancel / 未知 status 一律按已取消展示
  const success = params.get('status') === 'success'
  const sessionId = params.get('session_id')
  const refreshUser = useSessionStore((s) => s.refreshUser)
  const [refreshing, setRefreshing] = useState(false)

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
              <div className="text-[19px] font-extrabold tracking-tight">{t('billing.return.successTitle')}</div>
              <div className="text-[12px] mt-3 leading-relaxed" style={{ color: 'var(--muted)' }}>
                {t('billing.return.successDesc')}
              </div>
              <div className="text-[11px] mt-2 leading-relaxed" style={{ color: 'var(--dim)' }}>
                {t('billing.return.refreshHint')}
              </div>
              {sessionId && (
                <div className="text-[10px] num mt-3 truncate" style={{ color: 'var(--dim)' }} title={sessionId}>
                  session: {sessionId}
                </div>
              )}
              <div className="flex gap-2 mt-6">
                <button
                  className="btn btn-acc !py-2 flex-1 text-[12px]"
                  disabled={refreshing}
                  onClick={() => void onRefresh()}
                >
                  {refreshing ? t('billing.return.refreshing') : t('billing.return.refresh')}
                </button>
              </div>
            </>
          ) : (
            // cancel / 未知 status：按已取消展示（不产生扣款）
            <>
              <div className="text-[19px] font-extrabold tracking-tight">{t('billing.return.cancelTitle')}</div>
              <div className="text-[12px] mt-3 leading-relaxed" style={{ color: 'var(--muted)' }}>
                {t('billing.return.cancelDesc')}
              </div>
            </>
          )}

          <div className="mt-6 pt-4 rule-t flex items-center gap-4 text-[12px]">
            <Link to="/pricing" className="font-bold" style={{ color: 'var(--acc)' }}>
              {t('billing.return.backPricing')}
            </Link>
            <Link to="/studio" className="font-bold" style={{ color: 'var(--muted)' }}>
              {t('billing.return.backStudio')}
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
