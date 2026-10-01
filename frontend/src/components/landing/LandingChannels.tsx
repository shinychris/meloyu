import { CHANNELS, DEPLOY_LABEL, type ChannelDeploy } from '../../lib/landing-data'
import { useT } from '../../i18n'
import { EqMark } from './EqMark'

const DEPLOY_COLOR: Record<ChannelDeploy, string> = {
  local: 'var(--dim)',
  cloud: 'var(--trk-key)',
  selfhost: 'var(--acc)',
  service: 'var(--warn)',
}

/** 七大生成通道矩阵 */
export default function LandingChannels() {
  const t = useT()
  return (
    <section id="channels" className="scroll-mt-20">
      <div className="label flex items-center gap-2"><EqMark />{t('landing.channels.label')}</div>
      <h2 className="text-2xl font-extrabold tracking-tight mt-2">{t('landing.channels.title')}</h2>
      <p className="text-base mt-2 max-w-[620px] text-muted">
        {t('landing.channels.desc')}
      </p>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-8">
        {CHANNELS.map((c) => (
          <div
            key={c.id}
            className="card p-5 flex flex-col hover:border-line-2 transition-colors"
            style={c.id === 'acestep_local' ? { borderColor: 'rgba(0,255,44,.4)' } : undefined}
          >
            <div className="flex items-center justify-between">
              <span className="text-base font-extrabold num text-dim">
                {c.no}
              </span>
              <span
                className="text-2xs font-bold px-1.5 py-0.5 border border-line-2 tracking-wide"
                style={{ color: DEPLOY_COLOR[c.deploy] }}
              >
                {t(DEPLOY_LABEL[c.deploy])}
              </span>
            </div>
            <div className="text-md font-bold mt-3 leading-snug">{t(c.name)}</div>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {c.tags.map((tag) => (
                <span key={tag} className="badge">
                  {t(tag)}
                </span>
              ))}
            </div>
            <p className="text-sm mt-3.5 leading-relaxed text-muted">
              {t(c.highlight)}
            </p>
          </div>
        ))}
        {/* 第八格：通道设计理念卡 */}
        <div className="p-5 flex flex-col justify-center border border-dashed border-line">
          <div className="label">{t('landing.channels.designLabel')}</div>
          <p className="text-sm mt-3 leading-relaxed text-muted">
            {t('landing.channels.designText')}
            <br />
            <span className="text-acc">{t('landing.channels.designAcc')}</span>
          </p>
        </div>
      </div>
    </section>
  )
}
