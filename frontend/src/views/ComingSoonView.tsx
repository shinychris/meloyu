import { useNavigate } from 'react-router-dom'
import { useT, type TranslationKey } from '../i18n'

type Kind = 'edit' | 'pitch'

const META: Record<Kind, { label: TranslationKey; title: TranslationKey; desc: TranslationKey; features: TranslationKey[] }> = {
  edit: {
    label: 'coming.edit.label',
    title: 'coming.edit.title',
    desc: 'coming.edit.desc',
    features: ['coming.edit.f1', 'coming.edit.f2', 'coming.edit.f3', 'coming.edit.f4'],
  },
  pitch: {
    label: 'coming.pitch.label',
    title: 'coming.pitch.title',
    desc: 'coming.pitch.desc',
    features: ['coming.pitch.f1', 'coming.pitch.f2', 'coming.pitch.f3', 'coming.pitch.f4'],
  },
}

/** 音频剪辑 / 修调 —— V2 占位页（编曲 /arrange 已于 v0.9.0 上线真实多轨编辑器） */
export default function ComingSoonView({ kind }: { kind: Kind }) {
  const meta = META[kind]
  const navigate = useNavigate()
  const t = useT()
  const title = t(meta.title)

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4 flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="label">{t(meta.label)}</div>
          <h1 className="text-[28px] font-extrabold tracking-tight mt-1">{title}</h1>
        </div>
        <span
          className="text-[11px] px-2 py-1 font-bold"
          style={{ background: 'var(--acc-dim)', color: 'var(--acc)' }}
        >
          {t('coming.badge')}
        </span>
      </header>

      <div className="rule-t flex-1 px-8 py-8 overflow-y-auto">
        <div className="border border-dashed py-14 text-center" style={{ borderColor: 'var(--line)' }}>
          <svg className="mx-auto" width="44" height="44" viewBox="0 0 44 44" fill="none">
            <rect x="4" y="18" width="4" height="12" fill="#2c2c2c" />
            <rect x="12" y="11" width="4" height="26" fill="#2c2c2c" />
            <rect x="20" y="5" width="4" height="34" fill="#00ff2c" />
            <rect x="28" y="13" width="4" height="22" fill="#2c2c2c" />
            <rect x="36" y="9" width="4" height="28" fill="#2c2c2c" />
          </svg>
          <div className="text-[14px] mt-4 font-semibold" style={{ color: 'var(--muted)' }}>
            {t('coming.soonTitle', { title })}
          </div>
          <div className="text-[11px] mt-2 leading-relaxed max-w-[560px] mx-auto" style={{ color: 'var(--dim)' }}>
            {t(meta.desc)}
          </div>
          <div className="flex gap-1.5 mt-5 justify-center flex-wrap px-4">
            {meta.features.map((f) => (
              <span key={f} className="chip acc-on" style={{ cursor: 'default' }}>{t(f)}</span>
            ))}
          </div>
          <div className="flex gap-2 mt-6 justify-center">
            <button className="btn btn-acc !py-2 !px-4 text-[12px] font-bold" onClick={() => navigate('/studio')}>
              {t('coming.backStudio')}
            </button>
            <button className="btn btn-ghost !py-2 !px-4 text-[12px]" onClick={() => navigate('/library')}>
              {t('coming.goLibrary')}
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}
