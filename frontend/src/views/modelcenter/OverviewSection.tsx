import { useModelCenter } from './context'
import { useT, type TranslationKey } from '../../i18n'

/** 概览分区（F-FE-09 拆分）：运行时状态 + 生产就绪检查。跳转由父视图传入。 */
export default function OverviewSection({ jump }: { jump: (id: string) => void }) {
  const t = useT()
  const { runtime, local, settings } = useModelCenter()
  const ollama = runtime?.ollama
  // 生产就绪检查：歌词引擎未配置（none，无兜底引擎）或歌曲引擎仍在离线合成兜底
  // （非 AI 算法引擎）即提示配置真实模型通道
  const lyricsReady = !!settings && settings.lyrics_backend !== 'none'
  const songReady = !!settings && settings.music_backend !== 'localsynth'

  const checkRows: Array<{
    ready: boolean
    engineLabel: TranslationKey
    okKey: TranslationKey
    fbKey: TranslationKey
    target: string
  }> = [
    {
      ready: lyricsReady,
      engineLabel: 'models.runtime.lyricsEngine',
      okKey: 'models.overview.lyricsOk',
      fbKey: 'models.overview.lyricsFallback',
      target: 'mc-lyrics',
    },
    {
      ready: songReady,
      engineLabel: 'models.runtime.songEngine',
      okKey: 'models.overview.songOk',
      fbKey: 'models.overview.songFallback',
      target: 'mc-music',
    },
  ]

  return (
    <section id="mc-overview">
      <div className="label mb-3">{t('models.nav.overview')}</div>

      {/* 运行时状态 */}
      <div className="card p-5 flex items-center gap-4 flex-wrap">
        <span className={`gen-dot w-2 h-2 rounded-full flex-none ${ollama?.running ? 'bg-acc' : 'bg-bad'}`} />
        <div className="flex-1 min-w-0">
          <div className="text-base font-bold">
            Ollama {ollama?.running ? t('models.runtime.running', { version: ollama.version || '?' }) : t('models.runtime.stopped')}
            {ollama?.running && (
              <span className="ml-2 text-xs font-normal text-dim">
                {ollama.host} · {t('models.runtime.localModels', { n: ollama.models_count })}
              </span>
            )}
          </div>
          <div className="text-xs mt-1 text-dim">
            {ollama?.running
              ? local?.error || t('models.runtime.ready')
              : ollama?.error || '—'}
          </div>
        </div>
        {!ollama?.running && (
          <div className="text-xs max-w-[360px] text-dim">
            {ollama?.install_hint}
          </div>
        )}
        <div className="text-right flex-none">
          <div className="label">{t('models.runtime.lyricsEngine')}</div>
          <div className="text-sm font-bold mt-1 text-acc">
            {runtime?.engine || '…'}
          </div>
          <div className="label mt-2">{t('models.runtime.songEngine')}</div>
          <div className="text-sm font-bold mt-1 text-acc">
            {runtime?.song_engine || '…'}
          </div>
          <div className="label mt-2">{t('models.overview.envLabel')}</div>
          <div className="text-xs font-bold mt-1 text-muted">
            {runtime ? (runtime.docker ? t('models.overview.envDocker') : t('models.overview.envHost')) : '…'}
          </div>
        </div>
      </div>

      {/* 生产就绪检查 */}
      {settings && (
        <div className="card mt-3 p-5">
          <div className="label mb-3">{t('models.overview.checkTitle')}</div>
          {checkRows.map((row) => (
            <div key={row.target} className="flex items-center gap-3 py-1.5 flex-wrap">
              <span className={`flex-none ${row.ready ? 'text-acc' : 'text-warn'}`}>
                {row.ready ? '✓' : '⚠'}
              </span>
              <span className="text-sm font-bold flex-none">{t(row.engineLabel)}</span>
              <span className={`text-xs flex-1 min-w-0 ${row.ready ? 'text-dim' : 'text-warn'}`}>
                {row.ready ? t(row.okKey) : t(row.fbKey)}
              </span>
              {!row.ready && (
                <button className="btn btn-sm flex-none" onClick={() => jump(row.target)}>
                  {t('models.overview.goConfigure')}
                </button>
              )}
            </div>
          ))}
          {runtime?.docker && (
            <div className="text-2xs mt-3 leading-relaxed text-dim">
              {t('models.overview.dockerHint')}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
