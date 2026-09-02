import { WORKFLOW_STEPS } from '../../lib/landing-data'
import { useT } from '../../i18n'

/** 创作四步（与工作台 StepBar 一致） */
export default function LandingWorkFlow() {
  const t = useT()
  return (
    <section>
      <div className="label">{t('landing.workflow.label')}</div>
      <h2 className="text-[26px] font-extrabold tracking-tight mt-2">{t('landing.workflow.title')}</h2>
      <p className="text-[13px] mt-2 max-w-[560px]" style={{ color: 'var(--muted)' }}>
        {t('landing.workflow.desc')}
      </p>
      <div className="grid md:grid-cols-4 gap-px mt-8" style={{ background: 'var(--line)' }}>
        {WORKFLOW_STEPS.map((s, i) => (
          <div
            key={s.no}
            className="p-6 relative group cursor-default transition-colors"
            style={{ background: 'var(--bg)' }}
          >
            <div className="flex items-baseline justify-between">
              <span className="text-[28px] font-extrabold num tracking-tight" style={{ color: 'var(--dim)' }}>
                {s.no}
              </span>
              {i < WORKFLOW_STEPS.length - 1 && (
                <span className="text-[16px] font-bold" style={{ color: 'var(--dim)' }}>
                  →
                </span>
              )}
            </div>
            <div className="text-[15px] font-bold mt-4 group-hover:text-white transition-colors">{t(s.title)}</div>
            <p className="text-[12px] mt-2.5 leading-relaxed" style={{ color: 'var(--muted)' }}>
              {t(s.desc)}
            </p>
          </div>
        ))}
      </div>
    </section>
  )
}
