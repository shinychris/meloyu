import { useState } from 'react'
import { useModelCenter } from './context'
import { ChannelCard, MUSIC_BACKENDS, MUSIC_GROUPS, inputCls } from './shared'
import { testMusic, testReplicate, updateLLMSettings, getModelsRuntime } from '../../api/models'
import type { ExternalTestResult, MusicBackend } from '../../types/api'
import { toast } from '../../stores/toast'
import { useT } from '../../i18n'

/**
 * 歌曲引擎分区（拆分）：通道卡 + 外部歌曲 API + Replicate Token。
 * 通道/端点草稿在共享 context（applyCatalogModel 等目录动作会写入本区块的
 * musicBackend/replicateKey）；测试与保存瞬态为本区块自持。
 */
export default function MusicSection() {
  const t = useT()
  const {
    settings, presets,
    setSettings, setRuntime,
    musicBackend, setMusicBackend,
    musicBase, setMusicBase, musicModel, setMusicModel,
    replicateKey, setReplicateKey,
  } = useModelCenter()
  // API Key 输入只在保存时消费（refreshAll 不重置，与拆分前一致）——本区块自持
  const [musicKey, setMusicKey] = useState('')
  const [musicTesting, setMusicTesting] = useState(false)
  const [musicTestResult, setMusicTestResult] = useState<ExternalTestResult | null>(null)
  const [musicSaving, setMusicSaving] = useState(false)
  const [replicateTesting, setReplicateTesting] = useState(false)
  const [replicateTestResult, setReplicateTestResult] = useState<ExternalTestResult | null>(null)
  const [replicateSaving, setReplicateSaving] = useState(false)

  const runMusicTest = async () => {
    if (!musicBase.trim()) {
      toast(t('models.music.baseUrlRequired'))
      return
    }
    setMusicTesting(true)
    setMusicTestResult(null)
    try {
      setMusicTestResult(await testMusic({
        base_url: musicBase.trim(), api_key: musicKey.trim(), model: musicModel.trim(),
      }))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setMusicTesting(false)
    }
  }

  const saveMusic = async (target: MusicBackend, extra: Record<string, string> = {}) => {
    if (target === 'api' && !(musicBase || extra.music_api_base_url)) {
      toast(t('models.music.needApi'))
      return
    }
    if (target === 'replicate'
        && !(settings?.replicate_api_token.has_key || replicateKey.trim())) {
      toast(t('models.music.needReplicateToken'))
      return
    }
    if ((target === 'replicate' || target === 'musicgen_local' || target === 'acestep_local'
        || target === 'mmax_local' || target === 'songgen_local')
        && !settings?.music_model) {
      toast(t('models.music.needModel'))
      return
    }
    setMusicSaving(true)
    try {
      const st = await updateLLMSettings({
        music_backend: target,
        ...(target === 'api'
          ? {
              music_api_base_url: musicBase.trim(),
              music_api_model: musicModel.trim(),
              ...(musicKey.trim() ? { music_api_key: musicKey.trim() } : {}),
            }
          : {}),
        ...extra,
      })
      setSettings(st)
      setMusicBackend(st.music_backend)
      setMusicKey('')
      const rt = await getModelsRuntime()
      setRuntime(rt)
      toast(t('models.music.switched', { engine: rt.song_engine }))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setMusicSaving(false)
    }
  }

  const runReplicateTest = async () => {
    if (!replicateKey.trim()) {
      toast(t('models.replicate.needToken'))
      return
    }
    setReplicateTesting(true)
    setReplicateTestResult(null)
    try {
      setReplicateTestResult(await testReplicate({ api_token: replicateKey.trim() }))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setReplicateTesting(false)
    }
  }

  const saveReplicate = async () => {
    if (!replicateKey.trim() && !settings?.replicate_api_token.has_key) {
      toast(t('models.replicate.needTokenSave'))
      return
    }
    setReplicateSaving(true)
    try {
      const st = await updateLLMSettings({
        ...(replicateKey.trim() ? { replicate_api_token: replicateKey.trim() } : {}),
      })
      setSettings(st)
      setReplicateKey('')
      const rt = await getModelsRuntime()
      setRuntime(rt)
      toast(st.replicate_api_token.has_key ? t('models.replicate.tokenSaved') : t('models.replicate.tokenCleared'))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setReplicateSaving(false)
    }
  }

  return (
    <section id="mc-music">
      <div className="label mb-1">{t('models.music.title')}</div>
      <p className="text-xs mb-3 text-dim">
        {t('models.music.sectionDesc')}
      </p>

      {MUSIC_GROUPS.map((g) => (
        <div key={g.labelKey} className="mb-4">
          <div className="label mb-2" style={g.fallback ? { color: 'var(--warn)' } : undefined}>
            {t(g.labelKey)}
          </div>
          <div className={g.items.length > 1 ? 'grid grid-cols-1 md:grid-cols-2 gap-3' : ''}>
            {g.items.map((value) => (
              <ChannelCard
                key={value}
                title={MUSIC_BACKENDS[value].title}
                desc={MUSIC_BACKENDS[value].desc}
                on={musicBackend === value}
                fallback={g.fallback}
                onClick={() => {
                  if (value === 'api' && !musicBase && settings?.music_backend !== 'api') {
                    toast(t('models.music.needApi'))
                    return
                  }
                  if (value === 'replicate' && settings?.music_backend !== 'replicate'
                      && !settings?.replicate_api_token.has_key) {
                    toast(t('models.music.needCatalogToken'))
                    return
                  }
                  if ((value === 'musicgen_local' || value === 'acestep_local'
                      || value === 'mmax_local' || value === 'songgen_local')
                      && !settings?.music_model) {
                    toast(t('models.music.needCatalogModel'))
                    return
                  }
                  setMusicBackend(value)
                }}
              />
            ))}
          </div>
        </div>
      ))}
      {musicBackend !== settings?.music_backend && (
        <div className="mt-1 mb-4 flex items-center gap-3">
          <button className="btn btn-acc" disabled={musicSaving} onClick={() => void saveMusic(musicBackend)}>
            {musicSaving ? t('models.chan.switching') : t('models.chan.apply')}
          </button>
          <span className="text-xs text-dim">
            {t('models.chan.musicEffect')}
          </span>
        </div>
      )}

      {/* 外部歌曲 API 配置 */}
      <div className="card p-5">
        <div className="flex flex-wrap gap-2 mb-4">
          {(presets?.music_api_presets || []).map((p) => (
            <span
              key={p.vendor}
              className="chip"
              title={`${p.base_url}${p.model_hint ? ` · ${p.model_hint}` : ''}`}
              onClick={() => setMusicBase(p.base_url)}
            >
              {p.vendor}
            </span>
          ))}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="col-span-2">
            <div className="label mb-1">{t('models.musicApi.baseUrl')}</div>
            <input
              className={`w-full px-3 py-2 text-sm ${inputCls}`}
              placeholder={t('models.musicApi.baseUrlPh')}
              value={musicBase}
              onChange={(e) => setMusicBase(e.target.value)}
            />
          </div>
          <div>
            <div className="label mb-1">
              API KEY{' '}
              {settings?.music_api_key.has_key && (
                <span className="text-dim">
                  {t('models.keySavedHint', { tail: settings.music_api_key.key_tail })}
                </span>
              )}
            </div>
            <input
              className={`w-full px-3 py-2 text-sm ${inputCls}`}
              type="password"
              placeholder={settings?.music_api_key.has_key ? t('models.keyKeepPh') : 'sk-…'}
              value={musicKey}
              onChange={(e) => setMusicKey(e.target.value)}
            />
          </div>
          <div>
            <div className="label mb-1">{t('models.musicApi.model')}</div>
            <input
              className={`w-full px-3 py-2 text-sm ${inputCls}`}
              placeholder={t('models.musicApi.modelPh')}
              value={musicModel}
              onChange={(e) => setMusicModel(e.target.value)}
            />
          </div>
        </div>
        <div className="flex items-center gap-3 mt-4 flex-wrap">
          <button className="btn" disabled={musicTesting} onClick={() => void runMusicTest()}>
            {musicTesting ? t('models.testing') : t('models.test')}
          </button>
          <button className="btn btn-acc" disabled={musicSaving} onClick={() => void saveMusic('api')}>
            {musicSaving ? t('models.saving') : t('models.save')}
          </button>
          {musicTestResult && (
            <span className={`text-xs ${musicTestResult.ok ? 'text-acc' : 'text-bad'}`}>
              {musicTestResult.ok ? '✓' : '✕'} {musicTestResult.message}
            </span>
          )}
        </div>
        <div className="text-2xs mt-3 leading-relaxed text-dim">
          {t('models.musicApi.note')}
        </div>
      </div>

      {/* Replicate Token 配置 */}
      <div className="card mt-3 p-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-end">
          <div>
            <div className="label mb-1">
              REPLICATE API TOKEN{' '}
              {settings?.replicate_api_token.has_key && (
                <span className="text-dim">
                  {t('models.keySavedHint', { tail: settings.replicate_api_token.key_tail })}
                </span>
              )}
            </div>
            <input
              className={`w-full px-3 py-2 text-sm ${inputCls}`}
              type="password"
              placeholder={settings?.replicate_api_token.has_key ? t('models.keyKeepPh') : t('models.replicate.tokenPh')}
              value={replicateKey}
              onChange={(e) => setReplicateKey(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button className="btn" disabled={replicateTesting} onClick={() => void runReplicateTest()}>
              {replicateTesting ? t('models.testing') : t('models.testToken')}
            </button>
            <button className="btn btn-acc" disabled={replicateSaving} onClick={() => void saveReplicate()}>
              {replicateSaving ? t('models.saving') : t('models.saveToken')}
            </button>
            {replicateTestResult && (
              <span className={`text-xs truncate ${replicateTestResult.ok ? 'text-acc' : 'text-bad'}`}>
                {replicateTestResult.ok ? '✓' : '✕'} {replicateTestResult.message}
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
