import { useStudioStore } from '../../stores/studio'
import type { Task } from '../../types/api'

/** 生成进度卡：阶段文案 + 百分比进度条 + 取消（阶段来自任务轮询 stage_label） */
export default function GenProgress({ task }: { task: Task | null }) {
  const cancelGeneration = useStudioStore((s) => s.cancelGeneration)
  const label = task?.stage_label || '排队中…'
  const pct = task?.progress ?? 0

  return (
    <div className="mt-3 card p-5">
      <div className="flex items-center gap-3">
        <span className="dot gen-dot" style={{ background: 'var(--acc)' }}></span>
        <span className="text-[13px] font-semibold">{label}</span>
        <span className="text-[11px] num ml-auto" style={{ color: 'var(--muted)' }}>
          {pct}%
        </span>
        <button
          className="btn btn-ghost !py-1 !px-2.5 text-[11px]"
          onClick={() => void cancelGeneration()}
          title="取消将全额退还积分"
        >
          取消
        </button>
      </div>
      <div className="h-[3px] mt-3" style={{ background: 'var(--bg3)' }}>
        <div
          className="h-full transition-all duration-200"
          style={{ width: `${pct}%`, background: 'var(--acc)' }}
        ></div>
      </div>
      <div className="text-[10px] mt-3" style={{ color: 'var(--dim)' }}>
        MusiCoT 结构规划 → 编曲生成 → 人声合成 → 母带渲染
      </div>
    </div>
  )
}
