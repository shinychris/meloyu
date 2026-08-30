import { useStudioStore } from '../../stores/studio'

/** 四步引导条（点亮逻辑复刻原型 markStep/refreshSteps） */
export default function StepBar() {
  const stepDone = useStudioStore((s) => s.stepDone)
  const submitting = useStudioStore((s) => s.submitting)
  const hasResult = useStudioStore((s) => s.candidates.length > 0)

  const doneList = ([1, 2, 3] as const).filter((n) => stepDone[n])
  const reached = Math.min(4, (doneList.length > 0 ? Math.max(...doneList) : 0) + 1)
  const active = submitting || hasResult ? 4 : reached

  const steps = [
    { n: 1, label: '描述灵感' },
    { n: 2, label: '歌词与结构' },
    { n: 3, label: '参数与模型' },
    { n: 4, label: '生成与精修' },
  ]

  return (
    <div className="stepbar mt-4">
      {steps.map((s, i) => (
        <div className="flex items-center" key={s.n}>
          {i > 0 && <div className="step-arrow"></div>}
          <div className={`step ${s.n === active ? 'on' : ''} ${stepDone[s.n as 1 | 2 | 3] && s.n !== 4 ? 'done' : ''}`}>
            <b>{String(s.n).padStart(2, '0')}</b>
            {s.label}
          </div>
        </div>
      ))}
    </div>
  )
}
