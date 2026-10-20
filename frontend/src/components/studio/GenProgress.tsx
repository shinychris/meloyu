import { useStudioStore } from '../../stores/studio'
import { useSessionStore } from '../../stores/session'
import { useT } from '../../i18n'
import type { Task } from '../../types/api'

/** 生成进度卡：阶段文案 + 百分比进度条 + 取消（阶段来自任务轮询 stage_label） */
export default function GenProgress({ task }: { task: Task | null }) {
  const t = useT()
  const cancelGeneration = useStudioStore((s) => s.cancelGeneration)
  // license（桌面买断）模式无积分退还语义，取消提示用中性文案（v0.17.0）
  const isLicense = useSessionStore((s) => s.license?.billing_mode === 'license')
  const label = task?.stage_label || t('studio.progress.queued')
  const pct = task?.progress ?? 0

  return (
    <div className="mt-3 card p-5">
      <div className="flex items-center gap-3">
        <span className="dot gen-dot" style={{ background: 'var(--acc)' }}></span>
        <span className="text-base font-semibold">{label}</span>
        <span className="text-xs num ml-auto text-muted">
          {pct}%
        </span>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => void cancelGeneration()}
          title={t(isLicense ? 'studio.progress.cancelTitleLocal' : 'studio.progress.cancelTitle')}
        >
          {t('common.cancel')}
        </button>
      </div>
      <div className="h-[3px] mt-3 bg-bg-3">
        <div
          className="h-full transition-all duration-200"
          style={{ width: `${pct}%`, background: 'var(--acc)' }}
        ></div>
      </div>
      <div className="text-2xs mt-3 text-dim">
        {t('studio.progress.pipeline')}
      </div>
    </div>
  )
}
