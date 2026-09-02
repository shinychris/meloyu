import { MODEL_CATALOG } from '../../lib/landing-data'
import { useT, type TranslationKey } from '../../i18n'

const HEADERS: TranslationKey[] = [
  'landing.models.col.model',
  'landing.models.col.score',
  'landing.models.col.params',
  'landing.models.col.vocals',
  'landing.models.col.maxDur',
  'landing.models.col.license',
  'landing.models.col.note',
]

/** 开源模型目录（与模型中心同源数据，参考分降序） */
export default function LandingModels() {
  const t = useT()
  return (
    <section id="models" className="scroll-mt-20">
      <div className="label">{t('landing.models.label')}</div>
      <h2 className="text-[26px] font-extrabold tracking-tight mt-2">{t('landing.models.title')}</h2>
      <p className="text-[13px] mt-2 max-w-[620px]" style={{ color: 'var(--muted)' }}>
        {t('landing.models.desc')}
      </p>
      <div className="card mt-8 overflow-x-auto">
        <table className="w-full text-[12px] min-w-[820px]">
          <thead>
            <tr style={{ color: 'var(--dim)' }}>
              {HEADERS.map((h) => (
                <th key={h} className="label text-left px-4 py-3 border-b font-bold" style={{ borderColor: 'var(--line)' }}>
                  {t(h)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {MODEL_CATALOG.map((m) => (
              <tr key={m.name} className="transition-colors hover:bg-[var(--bg2)]">
                <td className="px-4 py-3 border-b" style={{ borderColor: 'var(--line)' }}>
                  <div className="font-bold">{m.name}</div>
                  <div className="text-[11px] mt-0.5" style={{ color: 'var(--dim)' }}>
                    {t(m.vendor)}
                  </div>
                </td>
                <td className="px-4 py-3 border-b num font-extrabold" style={{ borderColor: 'var(--line)', color: 'var(--acc)' }}>
                  {m.score.toFixed(1)}
                </td>
                <td className="px-4 py-3 border-b num" style={{ borderColor: 'var(--line)', color: 'var(--muted)' }}>
                  {t(m.params)}
                </td>
                <td className="px-4 py-3 border-b" style={{ borderColor: 'var(--line)' }}>
                  {m.vocals ? (
                    <span className="text-[10px] font-bold px-1.5 py-0.5" style={{ background: 'var(--acc-dim)', color: 'var(--acc)' }}>
                      {t('landing.models.vocals.yes')}
                    </span>
                  ) : (
                    <span className="text-[10px]" style={{ color: 'var(--dim)' }}>
                      {t('landing.models.vocals.no')}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 border-b num" style={{ borderColor: 'var(--line)', color: 'var(--muted)' }}>
                  {m.maxDur}
                </td>
                <td className="px-4 py-3 border-b" style={{ borderColor: 'var(--line)', color: 'var(--muted)' }}>
                  {t(m.license)}
                </td>
                <td className="px-4 py-3 border-b" style={{ borderColor: 'var(--line)', color: 'var(--dim)' }}>
                  {m.note ? t(m.note) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] mt-3" style={{ color: 'var(--dim)' }}>
        {t('landing.models.footnote')}
      </p>
    </section>
  )
}
