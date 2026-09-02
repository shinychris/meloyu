import { CHANNELS, DEPLOY_LABEL, type ChannelDeploy } from '../../lib/landing-data'
import { useT } from '../../i18n'

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
      <div className="label">{t('landing.channels.label')}</div>
      <h2 className="text-[26px] font-extrabold tracking-tight mt-2">{t('landing.channels.title')}</h2>
      <p className="text-[13px] mt-2 max-w-[620px]" style={{ color: 'var(--muted)' }}>
        {t('landing.channels.desc')}
      </p>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-8">
        {CHANNELS.map((c) => (
          <div
            key={c.id}
            className="card p-5 flex flex-col hover:border-[var(--line2)] transition-colors"
            style={c.id === 'acestep_local' ? { borderColor: 'rgba(0,255,44,.4)' } : undefined}
          >
            <div className="flex items-center justify-between">
              <span className="text-[13px] font-extrabold num" style={{ color: 'var(--dim)' }}>
                {c.no}
              </span>
              <span
                className="text-[10px] font-bold px-1.5 py-0.5 border tracking-wide"
                style={{ color: DEPLOY_COLOR[c.deploy], borderColor: 'var(--line2)' }}
              >
                {t(DEPLOY_LABEL[c.deploy])}
              </span>
            </div>
            <div className="text-[15px] font-bold mt-3 leading-snug">{t(c.name)}</div>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {c.tags.map((tag) => (
                <span key={tag} className="text-[10px] px-1.5 py-0.5" style={{ background: 'var(--bg3)', color: 'var(--muted)' }}>
                  {t(tag)}
                </span>
              ))}
            </div>
            <p className="text-[12px] mt-3.5 leading-relaxed" style={{ color: 'var(--muted)' }}>
              {t(c.highlight)}
            </p>
          </div>
        ))}
        {/* 第八格：通道设计理念卡 */}
        <div className="p-5 flex flex-col justify-center border border-dashed" style={{ borderColor: 'var(--line)' }}>
          <div className="label">{t('landing.channels.designLabel')}</div>
          <p className="text-[12px] mt-3 leading-relaxed" style={{ color: 'var(--muted)' }}>
            {t('landing.channels.designText')}
            <br />
            <span style={{ color: 'var(--acc)' }}>{t('landing.channels.designAcc')}</span>
          </p>
        </div>
      </div>
    </section>
  )
}
