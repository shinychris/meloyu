import { useModelCenter } from './context'
import type { MusicCatalogModel } from '../../types/api'
import { useT } from '../../i18n'

/**
 * 本地组件中心分区（v0.16.0 桌面按需下载，方案 §3.2；F-FE-09 拆分）：
 * 内置引擎 / MusicGen / ACE-Step 三卡；部署进度与下载动作共享 context 执行态。
 */
export default function ComponentsSection() {
  const t = useT()
  const {
    catalog, activeOp, catalogBusy,
    startAceDeploy, downloadMusicModel, removeMusicModel,
  } = useModelCenter()

  const musicgenModels = (catalog?.models ?? []).filter((m) => m.channels.includes('musicgen_local'))
  const acestepModels = (catalog?.models ?? []).filter((m) => m.channels.includes('acestep_local'))
  const minSizeMb = (channel: 'musicgen_local' | 'acestep_local') => {
    const list = channel === 'musicgen_local' ? musicgenModels : acestepModels
    return list.length ? Math.min(...list.map((m) => m.local_size_mb)) : 0
  }
  const compStatusBadge = (engine: 'musicgen' | 'acestep') => {
    const deps = engine === 'musicgen'
      ? catalog?.machine.musicgen_deps_installed
      : catalog?.machine.acestep_deps_installed
    const models = engine === 'musicgen' ? musicgenModels : acestepModels
    if (!deps) return <span className="badge" style={{ color: 'var(--bad)' }}>{t('models.comp.status.depsMissing')}</span>
    if (models.some((m) => m.local_status === 'ready')) {
      return <span className="badge" style={{ color: 'var(--acc)' }}>{t('models.comp.status.ready')}</span>
    }
    return <span className="badge">{t('models.comp.status.notDownloaded')}</span>
  }
  const compModelRow = (m: MusicCatalogModel) => (
    <div key={m.id} className="flex items-center gap-2 flex-wrap">
      <span className="text-xs text-muted flex-1 min-w-0 truncate" title={m.name}>{m.name}</span>
      <span className={`text-2xs num flex-none ${m.local_status === 'ready' ? 'text-acc' : 'text-dim'}`}>
        {m.local_status === 'ready' ? t('models.comp.status.ready') : `≈${m.local_size_mb}MB`}
      </span>
      {m.local_status === 'ready' ? (
        <button
          className="btn btn-sm flex-none"
          style={{ color: 'var(--bad)' }}
          disabled={catalogBusy}
          onClick={() => void removeMusicModel(m)}
        >
          {t('common.delete')}
        </button>
      ) : (
        <button
          className="btn btn-acc btn-sm flex-none"
          disabled={catalogBusy || !!activeOp}
          onClick={() => void downloadMusicModel(m)}
        >
          {t('models.catalog.downloadSize', { size: m.local_size_mb })}
        </button>
      )}
    </div>
  )

  return (
    <section id="mc-components" className="mt-10 scroll-mt-4">
      <div className="label mb-1">{t('models.comp.label')}</div>
      <div className="text-xs mb-3 max-w-[720px] text-dim leading-relaxed">
        {t('models.comp.desc')}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 items-stretch">
        {/* 内置引擎：随包分发，恒可用 */}
        <div className="card p-5 flex flex-col">
          <div className="flex items-center justify-between gap-2">
            <div className="text-base font-bold">{t('models.comp.builtin.title')}</div>
            <span className="badge badge-solid">{t('models.comp.status.builtin')}</span>
          </div>
          <div className="text-xs mt-2 text-muted leading-relaxed">
            {t('models.comp.builtin.desc')}
          </div>
          <div className="text-2xs mt-auto pt-4 text-dim">
            {t('models.comp.builtin.req')}
          </div>
        </div>

        {/* MusicGen 组件 */}
        <div className="card p-5 flex flex-col">
          <div className="flex items-center justify-between gap-2">
            <div className="text-base font-bold">{t('models.comp.musicgen.title')}</div>
            {compStatusBadge('musicgen')}
          </div>
          <div className="text-xs mt-2 text-muted leading-relaxed">
            {t('models.comp.musicgen.desc')}
          </div>
          <div className="text-2xs mt-2 text-dim leading-relaxed">
            {t('models.comp.musicgen.req', { size: String(minSizeMb('musicgen_local')) })}
          </div>
          {catalog && !catalog.machine.musicgen_deps_installed && (
            <div className="text-2xs mt-2 text-warn leading-relaxed break-words">
              {t('models.comp.depsHint', { hint: catalog.machine.install_hint })}
            </div>
          )}
          <div className="mt-auto pt-4 space-y-1.5">
            {musicgenModels.map((m) => compModelRow(m))}
          </div>
        </div>

        {/* ACE-Step 组件 */}
        <div className="card p-5 flex flex-col">
          <div className="flex items-center justify-between gap-2">
            <div className="text-base font-bold">{t('models.comp.acestep.title')}</div>
            {compStatusBadge('acestep')}
          </div>
          <div className="text-xs mt-2 text-muted leading-relaxed">
            {t('models.comp.acestep.desc')}
          </div>
          <div className="text-2xs mt-2 text-dim leading-relaxed">
            {t('models.comp.acestep.req')}
          </div>
          {catalog && !catalog.machine.acestep_deps_installed && (() => {
            // 组件部署进度（v0.16.3）：首启自动/手动共用 ops 管线；
            // activeOp 为本视图轮询态（实时），目录快照兜底
            const dop = activeOp?.op_type === 'acestep_deploy'
              ? activeOp
              : catalog.machine.acestep_deploy_op ?? null
            if (dop && (dop.status === 'queued' || dop.status === 'running')) {
              return (
                <div className="mt-2">
                  <div className="flex items-center justify-between text-2xs mb-1">
                    <span className="font-bold text-acc">{t('models.comp.deploying')}</span>
                    <span className="num text-acc">{dop.progress}%</span>
                  </div>
                  <div className="h-[4px] bg-bg-3">
                    <div
                      className="h-full transition-all bg-acc"
                      style={{ width: `${dop.progress}%` }}
                    />
                  </div>
                  <div className="text-2xs mt-1 text-dim break-words">{dop.message}</div>
                </div>
              )
            }
            return (
              <>
                {dop?.status === 'failed' && !!dop.error_message && (
                  <div className="text-2xs mt-2 text-bad leading-relaxed break-words">
                    {t('models.comp.deployFailed', { err: dop.error_message })}
                  </div>
                )}
                <button
                  className="btn btn-acc btn-sm mt-2 self-start"
                  disabled={catalogBusy || !!activeOp}
                  onClick={() => void startAceDeploy()}
                >
                  {dop?.status === 'failed'
                    ? t('models.comp.deployRetry')
                    : t('models.comp.deploy')}
                </button>
                <div className="text-2xs mt-2 text-warn leading-relaxed break-words">
                  {t('models.comp.depsHint', { hint: catalog.machine.acestep_install_hint })}
                </div>
              </>
            )
          })()}
          <div className="mt-auto pt-4 space-y-1.5">
            {acestepModels.map((m) => compModelRow(m))}
          </div>
        </div>
      </div>
    </section>
  )
}
