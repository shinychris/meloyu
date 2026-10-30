import { useModelCenter } from './context'
import { localChannelOf, localStatusText, LOCAL_CHANNELS, DOWNLOAD_CHANNELS, inputCls } from './shared'
import { getModelsRuntime, getMusicCatalog, updateLLMSettings } from '../../api/models'
import type { MusicBackend, MusicCatalogModel } from '../../types/api'
import { toast } from '../../stores/toast'
import { useT } from '../../i18n'

/**
 * 开源歌曲模型目录分区（F-FE-09 拆分）：目录卡（云端/本机/自托管使用、下载/删除、
 * slug 与自托管端点编辑）。slug/host 草稿与 replicateKey 在共享 context——
 * 目录动作与歌词/歌曲分区的保存动作按拆分前语义联动。
 */
export default function CatalogSection() {
  const t = useT()
  const {
    catalog, settings, setSettings, setRuntime, setCatalog,
    setMusicBackend,
    slugEdits, setSlugEdits, hostEdits, setHostEdits,
    replicateKey, setReplicateKey,
    catalogBusy, setCatalogBusy, activeOp,
    downloadMusicModel, removeMusicModel,
  } = useModelCenter()

  /** 使用目录模型：后端按模型通道自动推断 music_backend（显式传入时优先） */
  const applyCatalogModel = async (m: MusicCatalogModel, channel?: MusicBackend) => {
    const hasLocal = m.channels.some((c) => LOCAL_CHANNELS.includes(c))
    if (channel === 'replicate' || (!channel && !hasLocal)) {
      if (!settings?.replicate_api_token.has_key && !replicateKey.trim()) {
        toast(t('models.music.replicateHostedNeedToken'))
        return
      }
    }
    setCatalogBusy(true)
    try {
      const st = await updateLLMSettings({
        music_model: m.id,
        ...(channel ? { music_backend: channel } : {}),
        ...(replicateKey.trim()
          ? { replicate_api_token: replicateKey.trim() } : {}),
      })
      setSettings(st)
      setMusicBackend(st.music_backend)
      setReplicateKey('')
      const [rt, cat] = await Promise.all([getModelsRuntime(), getMusicCatalog()])
      setRuntime(rt)
      setCatalog(cat)
      toast(t('models.music.switched', { engine: rt.song_engine }))
    } catch {
      /* 拦截器已 toast（缺 Token / 通道不匹配等） */
    } finally {
      setCatalogBusy(false)
    }
  }

  const saveSlugs = async () => {
    setCatalogBusy(true)
    try {
      const st = await updateLLMSettings({ replicate_slugs: slugEdits })
      setSettings(st)
      const cat = await getMusicCatalog()
      setCatalog(cat)
      toast(t('models.catalog.slugsSaved'))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setCatalogBusy(false)
    }
  }

  /** 保存自托管服务端点（channel → base_url，空串=回退默认端口） */
  const saveHost = async (channel: MusicBackend) => {
    setCatalogBusy(true)
    try {
      const st = await updateLLMSettings({
        local_service_hosts: { [channel]: (hostEdits[channel] ?? '').trim() },
      })
      setSettings(st)
      const cat = await getMusicCatalog()
      setCatalog(cat)
      const svc = cat.machine.services?.[channel]
      toast(svc?.running ? t('models.catalog.hostSavedOnline', { detail: svc.detail }) : t('models.catalog.hostSavedOffline'))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setCatalogBusy(false)
    }
  }

  return (
    <section id="mc-catalog" className="mt-10 scroll-mt-4">
      <div className="label mb-1">{t('models.catalog.title')}</div>
      <p className="text-xs mb-3 text-dim">
        {t('models.catalog.sectionDesc')}
      </p>

      {catalog && !catalog.machine.musicgen_deps_installed && (
        <div className="card p-4 text-xs leading-relaxed text-dim">
          {t('models.catalog.musicgenDeps', { hint: catalog.machine.install_hint })}
        </div>
      )}
      {catalog && !catalog.machine.acestep_deps_installed && (
        <div className="card p-4 mt-2 text-xs leading-relaxed text-dim">
          {t('models.catalog.acestepDeps', { hint: catalog.machine.acestep_install_hint })}
        </div>
      )}

      {/* 目录列表 */}
      <div className="mt-3 space-y-3">
        {(catalog?.models || []).map((m) => {
          const st = localStatusText(m)
          const localChannel = localChannelOf(m)
          const isService = !!localChannel && !DOWNLOAD_CHANNELS.includes(localChannel)
          return (
            <div key={m.id} className="card p-4" style={m.selected ? { borderColor: 'var(--acc)' } : undefined}>
              <div className="flex items-start gap-3 flex-wrap">
                <span className="badge num flex-none" title={t('models.catalog.rankTitle')}>
                  #{m.rank}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-base font-bold">{m.name}</span>
                    <span
                      className="badge badge-acc num"
                      title={t('models.catalog.sourceTitle', { source: m.benchmark.source, notes: m.benchmark.notes })}
                    >
                      {t('models.catalog.score', { score: m.benchmark.score.toFixed(1) })}
                    </span>
                    {m.recommended && (
                      <span className="badge badge-solid" title={m.recommend_reason}>
                        {t('models.catalog.recommended')}
                      </span>
                    )}
                    {m.selected && (
                      <span className="badge badge-solid">{t('models.chan.inUse')}</span>
                    )}
                    <span className={`text-2xs ${st.cls}`}>{st.text}</span>
                  </div>
                  <div className="text-xs mt-1 text-dim">
                    {m.vendor} · {m.params} · {m.license}
                  </div>
                  <div className="flex gap-1.5 mt-2 flex-wrap">
                    <span className="badge">
                      {m.capabilities.vocals ? t('models.catalog.capVocals') : t('models.catalog.capInstrumental')}
                    </span>
                    <span className="badge">
                      ≤{m.capabilities.max_duration_sec}s
                    </span>
                    <span className="badge">
                      {m.capabilities.languages}
                    </span>
                    <span className="badge">
                      {localChannel ? t('models.catalog.chanLocal') : t('models.catalog.chanReplicate')}
                    </span>
                  </div>
                  <div className="text-2xs mt-1.5 leading-relaxed text-dim">
                    {m.benchmark.notes}{m.local_note ? ` · ${m.local_note}` : ''}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-none flex-wrap">
                  {m.channels.includes('replicate') && (
                    <button
                      className="btn btn-sm"
                      disabled={catalogBusy || m.selected}
                      onClick={() => void applyCatalogModel(m, 'replicate')}
                    >
                      {t('models.catalog.useCloud')}
                    </button>
                  )}
                  {localChannel && !isService && (
                    <>
                      <button
                        className="btn btn-sm"
                        disabled={catalogBusy || m.selected}
                        onClick={() => void applyCatalogModel(m, localChannel)}
                      >
                        {t('models.catalog.useLocal')}
                      </button>
                      {m.local_status !== 'ready' ? (
                        <button
                          className="btn btn-acc btn-sm"
                          disabled={catalogBusy || !!activeOp}
                          onClick={() => void downloadMusicModel(m)}
                        >
                          {t('models.catalog.downloadSize', { size: m.local_size_mb })}
                        </button>
                      ) : (
                        <button
                          className="btn btn-sm"
                          style={{ color: 'var(--bad)' }}
                          disabled={catalogBusy}
                          onClick={() => void removeMusicModel(m)}
                        >
                          {t('common.delete')}
                        </button>
                      )}
                    </>
                  )}
                  {isService && localChannel && (
                    <button
                      className="btn btn-sm"
                      disabled={catalogBusy || m.selected}
                      onClick={() => void applyCatalogModel(m, localChannel)}
                    >
                      {t('models.catalog.useSelfHosted')}
                    </button>
                  )}
                </div>
              </div>
              {m.channels.includes('replicate') && (
                <div className="flex items-center gap-2 mt-3" title={t('models.catalog.slugTitle')}>
                  <span className="text-2xs flex-none text-dim">slug</span>
                  <input
                    className={`flex-1 px-2 py-1 text-xs ${inputCls}`}
                    placeholder={m.replicate_slug_default || t('models.catalog.slugPh')}
                    value={slugEdits[m.id] ?? ''}
                    onChange={(e) => setSlugEdits({ ...slugEdits, [m.id]: e.target.value })}
                  />
                  {m.replicate_slug_overridden && (
                    <span className="text-2xs flex-none text-dim">{t('models.catalog.overridden')}</span>
                  )}
                </div>
              )}
              {isService && localChannel && (
                <div className="mt-3" title={t('models.catalog.hostTitle')}>
                  <div className="flex items-center gap-2">
                    <span className="text-2xs flex-none text-dim">{t('models.catalog.endpoint')}</span>
                    <input
                      className={`flex-1 px-2 py-1 text-xs ${inputCls}`}
                      placeholder={catalog?.machine.services?.[localChannel]?.host || 'http://127.0.0.1:…'}
                      value={hostEdits[localChannel] ?? ''}
                      onChange={(e) => setHostEdits({ ...hostEdits, [localChannel]: e.target.value })}
                    />
                    <button
                      className="btn btn-sm flex-none"
                      disabled={catalogBusy}
                      onClick={() => void saveHost(localChannel)}
                    >
                      {t('models.catalog.saveEndpoint')}
                    </button>
                  </div>
                  <div className={`text-2xs mt-1 ${m.local_status === 'ready' ? 'text-acc' : 'text-dim'}`}>
                    {m.service_detail || catalog?.machine.services?.[localChannel]?.detail}
                    {m.local_status !== 'ready' && catalog?.machine.services?.[localChannel]?.hint
                      ? t('models.catalog.hintSuffix', { hint: catalog.machine.services[localChannel].hint }) : ''}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
      <div className="flex items-center gap-3 mt-3 flex-wrap">
        <button className="btn" disabled={catalogBusy} onClick={() => void saveSlugs()}>
          {t('models.catalog.saveSlugs')}
        </button>
        <span className="text-2xs flex-1 text-dim">
          {catalog?.disclaimer}
        </span>
      </div>
    </section>
  )
}
