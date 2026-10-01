import { MODEL_CATALOG } from '../../lib/landing-data'
import { useT, type TranslationKey } from '../../i18n'
import { EqMark } from './EqMark'

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
      <div className="label flex items-center gap-2"><EqMark />{t('landing.models.label')}</div>
      <h2 className="text-2xl font-extrabold tracking-tight mt-2">{t('landing.models.title')}</h2>
      <p className="text-base mt-2 max-w-[620px] text-muted">
        {t('landing.models.desc')}
      </p>
      <div className="card mt-8 overflow-x-auto">
        <table className="w-full text-sm min-w-[820px]">
          <thead>
            <tr className="text-dim">
              {HEADERS.map((h) => (
                <th key={h} className="label text-left px-4 py-3 border-b border-line font-bold">
                  {t(h)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {MODEL_CATALOG.map((m) => (
              <tr key={m.name} className="transition-colors hover:bg-bg-2">
                <td className="px-4 py-3 border-b border-line">
                  <div className="font-bold">{m.name}</div>
                  <div className="text-xs mt-0.5 text-dim">{t(m.vendor)}</div>
                </td>
                <td className="px-4 py-3 border-b border-line num font-extrabold text-acc">{m.score.toFixed(1)}</td>
                <td className="px-4 py-3 border-b border-line num text-muted">{t(m.params)}</td>
                <td className="px-4 py-3 border-b border-line">
                  {m.vocals ? (
                    <span className="badge badge-acc">{t('landing.models.vocals.yes')}</span>
                  ) : (
                    <span className="text-2xs text-dim">{t('landing.models.vocals.no')}</span>
                  )}
                </td>
                <td className="px-4 py-3 border-b border-line num text-muted">{m.maxDur}</td>
                <td className="px-4 py-3 border-b border-line text-muted">{t(m.license)}</td>
                <td className="px-4 py-3 border-b border-line text-dim">{m.note ? t(m.note) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs mt-3 text-dim">
        {t('landing.models.footnote')}
      </p>
    </section>
  )
}
