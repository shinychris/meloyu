import type { ReactNode } from 'react'
import { CAPABILITIES } from '../../lib/landing-data'
import { useT } from '../../i18n'
import { EqMark } from './EqMark'

/** 能力卡图标：16px 直角线条风格（复用全站无圆角语言） */
const ICONS: Record<string, ReactNode> = {
  gen: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="1.5" y="1.5" width="13" height="13" />
      <path d="M4.5 10.5v-3M7.5 11.5v-7M10.5 10.5v-4" />
    </svg>
  ),
  edit: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="1.5" y="1.5" width="13" height="13" />
      <path d="M4.5 11.5l5-5 2 2-5 5H4.5v-2z" />
    </svg>
  ),
  export: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M8 10.5V2M5 5l3-3 3 3" />
      <path d="M2 10.5v3h12v-3" />
    </svg>
  ),
  lyrics: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="2" width="12" height="12" />
      <path d="M5 6h6M5 8.5h6M5 11h3.5" />
    </svg>
  ),
  rights: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M8 1.5l5.5 2v4c0 3.5-2.5 6-5.5 7-3-1-5.5-3.5-5.5-7v-4l5.5-2z" />
      <path d="M5.5 8l2 2 3-3.5" />
    </svg>
  ),
  engine: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 6l3-3 3 3 3-3 3 3-3 3 3 3-3 3-3-3-3 3-3-3 3-3-3-3z" />
    </svg>
  ),
}

/** 音轨六色做 icon 点缀，保持工作台的音轨色语言 */
const ICON_COLORS = ['var(--color-acc)', 'var(--color-trk-vox)', 'var(--color-trk-key)', 'var(--color-trk-drm)', 'var(--color-trk-str)', 'var(--color-trk-bas)']

/** 核心能力六卡 */
export default function LandingCapabilities() {
  const t = useT()
  return (
    <section id="features" className="scroll-mt-20">
      <div className="label flex items-center gap-2"><EqMark />{t('landing.capabilities.label')}</div>
      <h2 className="text-2xl font-extrabold tracking-tight mt-2">{t('landing.capabilities.title')}</h2>
      <p className="text-base mt-2 max-w-[560px] text-muted">
        {t('landing.capabilities.desc')}
      </p>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-8">
        {CAPABILITIES.map((c, i) => (
          <div
            key={c.title}
            className="card p-6 hover:border-line-2 transition-colors"
          >
            <div className="w-8 h-8 flex items-center justify-center border border-line-2" style={{ color: ICON_COLORS[i] }}>
              <span className="w-4 h-4 block">{ICONS[c.icon]}</span>
            </div>
            <div className="text-md font-bold mt-4">{t(c.title)}</div>
            <p className="text-sm mt-2 leading-relaxed text-muted">
              {t(c.desc)}
            </p>
          </div>
        ))}
      </div>
    </section>
  )
}
