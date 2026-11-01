import { useState } from 'react'
import { useModelCenter } from './context'
import { ChannelCard, BACKENDS, LYRICS_GROUPS, inputCls, fmtSize } from './shared'
import { testExternal, updateLLMSettings, getModelsRuntime, getLocalModels } from '../../api/models'
import type { ExternalTestResult } from '../../types/api'
import { toast } from '../../stores/toast'
import { useT } from '../../i18n'

/**
 * 歌词引擎分区（F-FE-09 拆分）：通道卡（Ollama 模型选择）+ Ollama 服务地址 +
 * 外部 API（OpenAI 兼容）。通道选择与端点草稿在共享 context（refreshAll 重置语义
 * 与拆分前一致）；连通性测试为纯本区块瞬态。
 */
export default function LyricsSection() {
  const t = useT()
  const {
    runtime, local, settings, presets,
    setRuntime, setLocal, setSettings,
    backend, setBackend, pickedModel, setPickedModel,
    extBase, setExtBase, extKey, setExtKey, extModel, setExtModel,
    ollamaHostEdit, setOllamaHostEdit,
    saving, setSaving, saveBackend,
  } = useModelCenter()
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<ExternalTestResult | null>(null)
  const [hostSaving, setHostSaving] = useState(false)

  const saveOllamaHost = async () => {
    const v = ollamaHostEdit.trim()
    if (!v) {
      toast(t('models.ollamaHost.required'))
      return
    }
    setHostSaving(true)
    try {
      const st = await updateLLMSettings({ ollama_host: v })
      setSettings(st)
      const [rt, lc] = await Promise.all([getModelsRuntime(), getLocalModels()])
      setRuntime(rt)
      setLocal(lc)
      setOllamaHostEdit(st.ollama_host)
      toast(t('models.ollamaHost.saved', { host: rt.ollama.host }))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setHostSaving(false)
    }
  }

  const runTest = async () => {
    if (!extBase.trim() || !extModel.trim()) {
      toast(t('models.ext.baseUrlRequired'))
      return
    }
    setTesting(true)
    setTestResult(null)
    try {
      setTestResult(await testExternal({
        base_url: extBase.trim(), api_key: extKey.trim(), model: extModel.trim(),
      }))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setTesting(false)
    }
  }

  const saveExternal = async () => {
    setSaving(true)
    try {
      const st = await updateLLMSettings({
        lyrics_backend: 'openai_compat',
        external_base_url: extBase.trim(),
        external_model: extModel.trim(),
        ...(extKey.trim() ? { external_api_key: extKey.trim() } : {}),
      })
      setSettings(st)
      setBackend('openai_compat')
      setExtKey('')
      const rt = await getModelsRuntime()
      setRuntime(rt)
      toast(t('models.lyrics.switched', { engine: rt.engine }))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setSaving(false)
    }
  }

  return (
    <section id="mc-lyrics">
      <div className="label mb-1">{t('models.lyrics.title')}</div>
      <p className="text-xs mb-3 text-dim">
        {t('models.lyrics.sectionDesc')}
      </p>

      {LYRICS_GROUPS.map((g) => (
        <div key={g.labelKey} className="mb-4">
          <div className="label mb-2" style={g.fallback ? { color: 'var(--warn)' } : undefined}>
            {t(g.labelKey)}
          </div>
          <div className={g.items.length > 1 ? 'grid grid-cols-1 md:grid-cols-2 gap-3' : ''}>
            {g.items.map((value) => (
              <ChannelCard
                key={value}
                title={BACKENDS[value].title}
                desc={BACKENDS[value].desc}
                on={backend === value}
                fallback={g.fallback}
                onClick={() => {
                  if (value === 'ollama' && !local?.models.length) {
                    toast(t('models.lyrics.noLocal'))
                    return
                  }
                  setBackend(value)
                }}
              >
                {value === 'ollama' && local && local.models.length > 0 && (
                  <select
                    className={`w-full mt-3 text-sm px-2 py-1.5 ${inputCls}`}
                    value={pickedModel}
                    onChange={(e) => {
                      setPickedModel(e.target.value)
                      if (backend === 'ollama') void saveBackend('ollama', { ollama_model: e.target.value })
                    }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {local.models.map((m) => (
                      <option key={m.name} value={m.name}>
                        {t('models.local.modelOption', { name: m.name, params: m.parameter_size || '?', size: fmtSize(m.size_bytes) })}
                      </option>
                    ))}
                  </select>
                )}
              </ChannelCard>
            ))}
          </div>
        </div>
      ))}
      {backend !== settings?.lyrics_backend && (
        <div className="mt-1 mb-4 flex items-center gap-3">
          <button className="btn btn-acc" disabled={saving} onClick={() => void saveBackend(backend)}>
            {saving ? t('models.chan.switching') : t('models.chan.apply')}
          </button>
          <span className="text-xs text-dim">
            {t('models.chan.lyricsEffect')}
          </span>
        </div>
      )}

      {/* Ollama 服务地址 */}
      <div className="card p-5">
        <div className="label mb-1">{t('models.ollamaHost.title')}</div>
        <div className="text-xs mb-3 text-dim">
          {t('models.ollamaHost.desc')}
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <input
            className={`flex-1 min-w-[280px] px-3 py-2 text-sm ${inputCls}`}
            placeholder={t('models.ollamaHost.ph')}
            value={ollamaHostEdit}
            onChange={(e) => setOllamaHostEdit(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void saveOllamaHost()
            }}
          />
          <button className="btn btn-acc flex-none" disabled={hostSaving} onClick={() => void saveOllamaHost()}>
            {hostSaving ? t('models.saving') : t('models.ollamaHost.save')}
          </button>
          {runtime && (
            <span className="text-xs flex-none text-dim">
              {t('models.ollamaHost.effective', { host: runtime.ollama.host })}
            </span>
          )}
        </div>
        {runtime?.docker && (
          <div className="text-2xs mt-3 leading-relaxed text-warn">
            {t('models.ollamaHost.dockerHint')}
          </div>
        )}
      </div>

      {/* 外部 API（OpenAI 兼容） */}
      <div className="card mt-3 p-5">
        <div className="label mb-3">{t('models.ext.title')}</div>
        <div className="flex flex-wrap gap-2 mb-4">
          {(presets?.external_presets || []).map((p) => (
            <span
              key={p.vendor}
              className="chip"
              title={`${p.base_url} · ${t('models.ext.recommended', { hint: p.model_hint })}`}
              onClick={() => {
                setExtBase(p.base_url)
                if (!extModel) setExtModel(p.model_hint.split('（')[0])
              }}
            >
              {p.vendor}
            </span>
          ))}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="col-span-2">
            <div className="label mb-1">BASE URL</div>
            <input
              className={`w-full px-3 py-2 text-sm ${inputCls}`}
              placeholder="https://open.bigmodel.cn/api/paas/v4"
              value={extBase}
              onChange={(e) => setExtBase(e.target.value)}
            />
          </div>
          <div>
            <div className="label mb-1">
              API KEY{' '}
              {settings?.external_api_key.has_key && (
                <span className="text-dim">
                  {t('models.keySavedHint', { tail: settings.external_api_key.key_tail })}
                </span>
              )}
            </div>
            <input
              className={`w-full px-3 py-2 text-sm ${inputCls}`}
              type="password"
              placeholder={settings?.external_api_key.has_key ? t('models.keyKeepPh') : 'sk-…'}
              value={extKey}
              onChange={(e) => setExtKey(e.target.value)}
            />
          </div>
          <div>
            <div className="label mb-1">MODEL</div>
            <input
              className={`w-full px-3 py-2 text-sm ${inputCls}`}
              placeholder="glm-4-flash / deepseek-chat / gpt-4o-mini"
              value={extModel}
              onChange={(e) => setExtModel(e.target.value)}
            />
          </div>
        </div>
        <div className="flex items-center gap-3 mt-4 flex-wrap">
          <button className="btn" disabled={testing} onClick={() => void runTest()}>
            {testing ? t('models.testing') : t('models.test')}
          </button>
          <button className="btn btn-acc" disabled={saving} onClick={() => void saveExternal()}>
            {saving ? t('models.saving') : t('models.save')}
          </button>
          {testResult && (
            <span className={`text-xs ${testResult.ok ? 'text-acc' : 'text-bad'}`}>
              {testResult.ok ? '✓' : '✕'} {testResult.message}
              {testResult.sample ? t('models.testEcho', { sample: testResult.sample }) : ''}
            </span>
          )}
        </div>
        <div className="text-2xs mt-3 text-dim">
          {t('models.ext.note')}
        </div>
      </div>
    </section>
  )
}
