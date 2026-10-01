import { WORKFLOW_STEPS } from '../../lib/landing-data'
import { useT } from '../../i18n'
import { EqMark } from './EqMark'

/** 创作四步（与工作台 StepBar 一致） */
export default function LandingWorkFlow() {
  const t = useT()
  return (
    <section>
      <div className="label flex items-center gap-2"><EqMark />{t('landing.workflow.label')}</div>
      <h2 className="text-2xl font-extrabold tracking-tight mt-2">{t('landing.workflow.title')}</h2>
      <p className="text-base mt-2 max-w-[560px] text-muted">
        {t('landing.workflow.desc')}
      </p>
      <div className="grid md:grid-cols-4 gap-px mt-8" style={{ background: 'var(--line)' }}>
        {WORKFLOW_STEPS.map((s, i) => (
          <div key={s.no} className="p-6 relative group cursor-default transition-colors bg-bg">
            <div className="flex items-baseline justify-between">
              <span className="text-3xl font-extrabold num tracking-tight text-dim">
                {s.no}
              </span>
              {i < WORKFLOW_STEPS.length - 1 && (
                <span className="text-lg font-bold text-dim">
                  →
                </span>
              )}
            </div>
            <div className="text-md font-bold mt-4 group-hover:text-white transition-colors">{t(s.title)}</div>
            <p className="text-sm mt-2.5 leading-relaxed text-muted">
              {t(s.desc)}
            </p>
          </div>
        ))}
      </div>
    </section>
  )
}
