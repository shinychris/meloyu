import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUiStore } from '../../stores/ui'
import { toast } from '../../stores/toast'
import { useT } from '../../i18n'
import type { TranslationKey } from '../../i18n'

interface ObStep {
  sel: string | null
  /** 步骤标题词条 */
  titleKey: TranslationKey
  /** 步骤描述词条 */
  descKey: TranslationKey
  /** 需要导航到的路由（引导目标所在视图） */
  view?: string
}

const OB_STEPS: ObStep[] = [
  {
    sel: '#inspireBox',
    view: '/studio',
    titleKey: 'layout.ob.step1.title',
    descKey: 'layout.ob.step1.desc',
  },
  {
    sel: '#lyricBox',
    view: '/studio',
    titleKey: 'layout.ob.step2.title',
    descKey: 'layout.ob.step2.desc',
  },
  {
    sel: '#btnGenerate',
    view: '/studio',
    titleKey: 'layout.ob.step3.title',
    descKey: 'layout.ob.step3.desc',
  },
  {
    sel: null,
    view: '/arrange',
    titleKey: 'layout.ob.step4.title',
    descKey: 'layout.ob.step4.desc',
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
  const t = useT()
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
            {t('layout.ob.progress', { current: onboardingStep + 1, total: OB_STEPS.length })}
          </span>
          <button className="text-2xs text-dim" onClick={endOnboarding}>
            {t('layout.ob.skip')}
          </button>
        </div>
        <div className="text-md font-bold mt-2">{t(step.titleKey)}</div>
        <div className="text-sm mt-2 leading-relaxed text-muted">
          {t(step.descKey)}
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
            className="btn btn-acc btn-sm font-bold"
            onClick={() => {
              if (isLast) {
                endOnboarding()
                toast(t('layout.ob.finished'))
              } else {
                setStep(onboardingStep + 1)
              }
            }}
          >
            {isLast ? t('common.done') : t('common.next')}
          </button>
        </div>
      </div>
    </>
  )
}
