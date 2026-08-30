import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUiStore } from '../../stores/ui'
import { toast } from '../../stores/toast'

interface ObStep {
  sel: string | null
  title: string
  desc: string
  /** 需要导航到的路由（引导目标所在视图） */
  view?: string
}

const OB_STEPS: ObStep[] = [
  {
    sel: '#inspireBox',
    view: '/studio',
    title: '描述你的灵感',
    desc: '点选场景、情绪、风格与主奏乐器，系统自动组装专业提示词；也可以直接改写下方描述。',
  },
  {
    sel: '#lyricBox',
    view: '/studio',
    title: '歌词与结构',
    desc: '粘贴歌词，用 [Verse]/[Chorus] 等标签告诉 AI 歌曲结构；没有歌词可在「歌词助手」里让 AI 起草。',
  },
  {
    sel: '#btnGenerate',
    view: '/studio',
    title: '生成与挑选',
    desc: '每次产出 2 个候选并给出 AI 质量分；不满意可整首重生成，或只对某段落局部重生成（V1.1）。',
  },
  {
    sel: null,
    view: '/arrange',
    title: '进入专业制作',
    desc: '满意的候选可「送往编曲」：多轨时间线编排、音频剪辑、修调将在 V2 上线；现在即可在作品库导出可商用的成品与授权证书。',
  },
]

interface SpotRect {
  left: number
  top: number
  width: number
  height: number
}

/** 新手引导 spotlight（复刻原型 obSteps：四步高亮 + 提示卡） */
export default function Onboarding() {
  const { onboardingOpen, onboardingStep, setStep, endOnboarding } = useUiStore()
  const navigate = useNavigate()
  const [spot, setSpot] = useState<SpotRect | null>(null)
  const [tipPos, setTipPos] = useState<{ left: number | string; top: number | string; centered: boolean }>({
    left: '50%',
    top: '50%',
    centered: true,
  })

  useEffect(() => {
    if (!onboardingOpen) return
    const step = OB_STEPS[Math.min(onboardingStep, OB_STEPS.length - 1)]
    if (step.view) navigate(step.view)
    // 等路由与渲染完成后测量
    const raf = window.requestAnimationFrame(() => {
      if (step.sel) {
        const el = document.querySelector(step.sel) as HTMLElement | null
        if (el) {
          const r = el.getBoundingClientRect()
          setSpot({ left: r.left - 6, top: r.top - 6, width: r.width + 12, height: r.height + 12 })
          let tx = r.left
          let ty = r.bottom + 14
          if (ty + 170 > window.innerHeight) ty = r.top - 175
          if (tx + 300 > window.innerWidth) tx = window.innerWidth - 316
          setTipPos({ left: Math.max(12, tx), top: Math.max(12, ty), centered: false })
          return
        }
      }
      setSpot(null)
      setTipPos({ left: '50%', top: '50%', centered: true })
    })
    return () => window.cancelAnimationFrame(raf)
  }, [onboardingOpen, onboardingStep, navigate])

  if (!onboardingOpen) return null
  const step = OB_STEPS[Math.min(onboardingStep, OB_STEPS.length - 1)]
  const isLast = onboardingStep === OB_STEPS.length - 1

  return (
    <>
      <div className="ob-mask on" onClick={endOnboarding}></div>
      <div
        className="ob-spot"
        style={
          spot
            ? { display: 'block', left: spot.left, top: spot.top, width: spot.width, height: spot.height }
            : undefined
        }
      ></div>
      <div
        className="ob-tip on"
        style={
          tipPos.centered
            ? { left: '50%', top: '50%', transform: 'translate(-50%,-50%)' }
            : { left: tipPos.left, top: tipPos.top }
        }
      >
        <div className="flex items-center justify-between">
          <span className="label" style={{ color: 'var(--acc)' }}>
            第 {onboardingStep + 1} / {OB_STEPS.length} 步
          </span>
          <button className="text-[10px]" style={{ color: 'var(--dim)' }} onClick={endOnboarding}>
            跳过
          </button>
        </div>
        <div className="text-[14px] font-bold mt-2">{step.title}</div>
        <div className="text-[12px] mt-2 leading-relaxed" style={{ color: 'var(--muted)' }}>
          {step.desc}
        </div>
        <div className="flex justify-between items-center mt-4">
          <div className="flex gap-1">
            {OB_STEPS.map((_, i) => (
              <span
                key={i}
                className="dot"
                style={{ background: i === onboardingStep ? 'var(--acc)' : 'var(--dim)' }}
              ></span>
            ))}
          </div>
          <button
            className="btn btn-acc !py-1.5 !px-4 text-[11px] font-bold"
            onClick={() => {
              if (isLast) {
                endOnboarding()
                toast('引导结束 · 随时可在左下角重新打开')
              } else {
                setStep(onboardingStep + 1)
              }
            }}
          >
            {isLast ? '完成' : '下一步'}
          </button>
        </div>
      </div>
    </>
  )
}
