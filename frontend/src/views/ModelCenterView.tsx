import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  ExternalTestResult,
  LLMSettings,
  LyricsBackend,
  ModelOpInfo,
  ModelsRuntime,
  MusicBackend,
  MusicCatalog,
  MusicCatalogModel,
} from '../types/api'
import {
  deleteModel,
  deleteMusicModel,
  getLLMSettings,
  getLocalModels,
  getModelOp,
  getModelsPresets,
  getModelsRuntime,
  getMusicCatalog,
  listModelOps,
  pullModel,
  pullMusicModel,
  testExternal,
  testMusic,
  testReplicate,
  updateLLMSettings,
} from '../api/models'
import type { LocalModelsResult, ModelsPresets } from '../types/api'
import { useConfirmStore } from '../stores/confirm'
import { toast } from '../stores/toast'
import { formatDateTime } from '../lib/format'

function fmtSize(bytes: number): string {
  if (!bytes) return '-'
  const gb = bytes / 1024 ** 3
  if (gb >= 1) return `${gb.toFixed(1)} GB`
  return `${Math.round(bytes / 1024 ** 2)} MB`
}

const BACKENDS: { value: LyricsBackend; title: string; desc: string }[] = [
  { value: 'localsynth', title: '本地规则引擎', desc: '离线可用 · 秒级出稿 · 演示级文采（默认）' },
  { value: 'ollama', title: '本地开源模型（Ollama）', desc: '真实大模型 · 数据不出本机 · 速度视模型与硬件' },
  { value: 'openai_compat', title: '外部 API（OpenAI 兼容）', desc: '智谱 / DeepSeek / OpenAI 等云端模型 · 需 API Key' },
]

const MUSIC_BACKENDS: { value: MusicBackend; title: string; desc: string }[] = [
  { value: 'localsynth', title: '本地合成引擎', desc: '离线可用 · 算法作曲实时渲染 · 含分轨/MIDI（默认）' },
  { value: 'acestep_local', title: '本机 ACE-Step v1.5（开源·人声成曲）', desc: '歌词→真人声演唱完整歌曲 · 独立 venv 部署 · 8GB 显存档 · GPU 约 1~3 分钟/首' },
  { value: 'replicate', title: 'Replicate 开源模型托管', desc: '多类开源歌曲模型（ACE-Step/YuE/MusicGen…）· 一个 Token 全可用' },
  { value: 'api', title: '外部歌曲 API（Suno 兼容）', desc: '商业整曲模型（人声演唱）· 需网关与 Key · 约 1~5 分钟/首' },
  { value: 'musicgen_local', title: '本机 MusicGen（开源）', desc: '本地真实下载与推理（器乐）· 免 API Key · CPU 可跑' },
]

/** 支持本机下载运行的通道（目录按钮/状态按此泛化渲染） */
const LOCAL_CHANNELS: MusicBackend[] = ['acestep_local', 'musicgen_local']
const localChannelOf = (m: MusicCatalogModel): MusicBackend | undefined =>
  m.channels.find((c) => LOCAL_CHANNELS.includes(c))

const OP_TYPE_LABEL: Record<ModelOpInfo['op_type'], string> = {
  pull: '下载', delete: '删除', music_pull: '下载', music_delete: '删除',
}

/** 目录模型的本机状态文案 */
function localStatusText(m: MusicCatalogModel): { text: string; color: string } {
  if (m.local_status === 'ready') return { text: '本机已就绪', color: 'var(--acc)' }
  if (m.local_status === 'deps_missing') return { text: '依赖未安装', color: 'var(--bad)' }
  if (m.local_status === 'not_downloaded') return { text: '未下载', color: 'var(--dim)' }
  return { text: '仅托管', color: 'var(--dim)' }
}

/** 模型中心：歌词引擎通道切换 + 本地开源模型下载管理 + 外部 API 配置（契约 §5.8） */
export default function ModelCenterView() {
  const confirm = useConfirmStore((s) => s.confirm)
  const [runtime, setRuntime] = useState<ModelsRuntime | null>(null)
  const [local, setLocal] = useState<LocalModelsResult | null>(null)
  const [settings, setSettings] = useState<LLMSettings | null>(null)
  const [presets, setPresets] = useState<ModelsPresets | null>(null)
  const [ops, setOps] = useState<ModelOpInfo[]>([])

  const [backend, setBackend] = useState<LyricsBackend>('localsynth')
  const [pickedModel, setPickedModel] = useState('')

  const [musicBackend, setMusicBackend] = useState<MusicBackend>('localsynth')
  const [musicBase, setMusicBase] = useState('')
  const [musicKey, setMusicKey] = useState('')
  const [musicModel, setMusicModel] = useState('')
  const [musicTesting, setMusicTesting] = useState(false)
  const [musicTestResult, setMusicTestResult] = useState<ExternalTestResult | null>(null)
  const [musicSaving, setMusicSaving] = useState(false)

  const [catalog, setCatalog] = useState<MusicCatalog | null>(null)
  const [replicateKey, setReplicateKey] = useState('')
  const [replicateTesting, setReplicateTesting] = useState(false)
  const [replicateTestResult, setReplicateTestResult] = useState<ExternalTestResult | null>(null)
  const [replicateSaving, setReplicateSaving] = useState(false)
  const [slugEdits, setSlugEdits] = useState<Record<string, string>>({})
  const [catalogBusy, setCatalogBusy] = useState(false)

  const [pullTag, setPullTag] = useState('')
  const [activeOp, setActiveOp] = useState<ModelOpInfo | null>(null)
  const [pulling, setPulling] = useState(false)

  const [extBase, setExtBase] = useState('')
  const [extKey, setExtKey] = useState('')
  const [extModel, setExtModel] = useState('')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<ExternalTestResult | null>(null)
  const [saving, setSaving] = useState(false)

  const pollRef = useRef<number | null>(null)

  const refreshAll = useCallback(async () => {
    const [rt, lc, st, ps, opList, cat] = await Promise.all([
      getModelsRuntime(), getLocalModels(), getLLMSettings(),
      getModelsPresets(), listModelOps(6), getMusicCatalog(),
    ])
    setRuntime(rt)
    setLocal(lc)
    setSettings(st)
    setPresets(ps)
    setOps(opList)
    setCatalog(cat)
    setBackend(st.lyrics_backend)
    setPickedModel(st.ollama_model || lc.models[0]?.name || '')
    setExtBase(st.external_base_url)
    setExtModel(st.external_model)
    setMusicBackend(st.music_backend)
    setMusicBase(st.music_api_base_url)
    setMusicModel(st.music_api_model)
    setSlugEdits(st.replicate_slugs || {})
  }, [])

  useEffect(() => {
    void refreshAll().catch(() => {
      /* 拦截器已 toast */
    })
  }, [refreshAll])

  // 下载进度轮询（2s，终态刷新列表与操作记录）
  useEffect(() => {
    if (!activeOp || (activeOp.status !== 'queued' && activeOp.status !== 'running')) {
      if (activeOp) {
        void refreshAll().catch(() => {})
        setActiveOp(null)
      }
      return
    }
    pollRef.current = window.setInterval(async () => {
      try {
        const op = await getModelOp(activeOp.id)
        setActiveOp(op)
      } catch {
        /* 下一轮重试 */
      }
    }, 2000)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [activeOp, refreshAll])

  const saveBackend = async (target: LyricsBackend, extra: Record<string, string> = {}) => {
    if (target === 'ollama' && !pickedModel && !extra.ollama_model) {
      toast('请先在下方选择（或下载）一个本地模型')
      return
    }
    if (target === 'openai_compat' && !(extBase || extra.external_base_url)) {
      toast('请先在下方完成外部 API 配置')
      return
    }
    setSaving(true)
    try {
      const st = await updateLLMSettings({
        lyrics_backend: target,
        ...(target === 'ollama' && pickedModel ? { ollama_model: pickedModel } : {}),
        ...(target === 'openai_compat'
          ? { external_base_url: extBase, external_model: extModel }
          : {}),
        ...extra,
      })
      setSettings(st)
      setBackend(st.lyrics_backend)
      const rt = await getModelsRuntime()
      setRuntime(rt)
      toast(`歌词引擎已切换：${rt.engine}`)
    } catch {
      /* 拦截器已 toast */
    } finally {
      setSaving(false)
    }
  }

  const startPull = async (tag: string) => {
    const model = tag.trim()
    if (!model) {
      toast('请输入或选择要下载的模型 tag')
      return
    }
    setPulling(true)
    try {
      const op = await pullModel(model)
      setActiveOp(op)
      setPullTag('')
      toast(`开始下载 ${model}`)
    } catch {
      /* 拦截器已 toast（重复下载 / 格式错误等） */
    } finally {
      setPulling(false)
    }
  }

  const removeModel = async (name: string) => {
    const ok = await confirm({
      title: `删除模型 ${name}？`,
      description: '将删除本机模型文件以释放磁盘空间；若是当前引擎所用模型，引擎将自动回退到本地规则。',
      confirmText: '删除',
      danger: true,
    })
    if (!ok) return
    try {
      const op = await deleteModel(name)
      if (op.status === 'succeeded') toast(`已删除 ${name}`)
      else toast(op.error_message || '删除失败', 'warn')
      await refreshAll()
    } catch {
      /* 拦截器已 toast */
    }
  }

  const runTest = async () => {
    if (!extBase.trim() || !extModel.trim()) {
      toast('base_url 与 model 必填')
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
      toast(`歌词引擎已切换：${rt.engine}`)
    } catch {
      /* 拦截器已 toast */
    } finally {
      setSaving(false)
    }
  }

  const runMusicTest = async () => {
    if (!musicBase.trim()) {
      toast('base_url 必填')
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
      toast('请先在下方完成外部歌曲 API 配置')
      return
    }
    if (target === 'replicate'
        && !(settings?.replicate_api_token.has_key || replicateKey.trim())) {
      toast('Replicate 通道需先保存 API Token（见下方开源模型目录）')
      return
    }
    if ((target === 'replicate' || target === 'musicgen_local' || target === 'acestep_local')
        && !settings?.music_model) {
      toast('请先在下方目录中选择一个开源模型')
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
      toast(`歌曲引擎已切换：${rt.song_engine}`)
    } catch {
      /* 拦截器已 toast */
    } finally {
      setMusicSaving(false)
    }
  }

  const runReplicateTest = async () => {
    if (!replicateKey.trim()) {
      toast('请先输入 Replicate API Token（r8_ 开头）')
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
      toast('请先输入 Replicate API Token')
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
      toast(st.replicate_api_token.has_key ? 'Replicate Token 已保存' : 'Replicate Token 已清除')
    } catch {
      /* 拦截器已 toast */
    } finally {
      setReplicateSaving(false)
    }
  }

  /** 使用目录模型：后端按模型通道自动推断 music_backend（显式传入时优先） */
  const useCatalogModel = async (m: MusicCatalogModel, channel?: MusicBackend) => {
    const hasLocal = m.channels.some((c) => LOCAL_CHANNELS.includes(c))
    if (channel === 'replicate' || (!channel && !hasLocal)) {
      if (!settings?.replicate_api_token.has_key && !replicateKey.trim()) {
        toast('该模型走 Replicate 托管，请先在下方保存 API Token')
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
      toast(`歌曲引擎已切换：${rt.song_engine}`)
    } catch {
      /* 拦截器已 toast（缺 Token / 通道不匹配等） */
    } finally {
      setCatalogBusy(false)
    }
  }

  const downloadMusicModel = async (m: MusicCatalogModel) => {
    setCatalogBusy(true)
    try {
      const op = await pullMusicModel(m.id)
      setActiveOp(op)
      toast(`开始下载 ${m.name}（约 ${m.local_size_mb} MB）`)
    } catch {
      /* 拦截器已 toast */
    } finally {
      setCatalogBusy(false)
    }
  }

  const removeMusicModel = async (m: MusicCatalogModel) => {
    const ok = await confirm({
      title: `删除本机模型 ${m.name}？`,
      description: '将删除 HuggingFace 缓存中的模型权重以释放磁盘空间；若是当前引擎所用模型，引擎将自动回退到本地合成。',
      confirmText: '删除',
      danger: true,
    })
    if (!ok) return
    try {
      const op = await deleteMusicModel(m.id)
      if (op.status === 'succeeded') toast(`已删除 ${m.name}`)
      else toast(op.error_message || '删除失败', 'warn')
      await refreshAll()
    } catch {
      /* 拦截器已 toast */
    }
  }

  const saveSlugs = async () => {
    setCatalogBusy(true)
    try {
      const st = await updateLLMSettings({ replicate_slugs: slugEdits })
      setSettings(st)
      const cat = await getMusicCatalog()
      setCatalog(cat)
      toast('slug 覆盖已保存')
    } catch {
      /* 拦截器已 toast */
    } finally {
      setCatalogBusy(false)
    }
  }

  const ollama = runtime?.ollama

  return (
    <div className="view h-full overflow-y-auto">
      <div className="max-w-[1080px] mx-auto px-10 py-8">
        <div className="label">模型中心 · MODEL HUB</div>
        <h1 className="text-[22px] font-extrabold tracking-tight mt-2">AI 引擎与模型管理</h1>
        <p className="text-[12px] mt-2" style={{ color: 'var(--dim)' }}>
          歌词引擎：本地规则（离线兜底）/ 本地开源模型（Ollama）/ 外部 API（OpenAI 兼容）；
          歌曲引擎：本机 ACE-Step v1.5（开源人声成曲）/ 本地合成（离线兜底）/ Replicate
          开源模型托管 / 外部歌曲 API / 本机 MusicGen——开源模型按外部测评参考分排序并给出推荐（见下方目录）。引擎失败时自动回退本地引擎，创作不中断。
        </p>

        {/* 运行时状态 */}
        <div className="card mt-6 p-5 flex items-center gap-4">
          <span
            className="gen-dot"
            style={{
              width: 8, height: 8, borderRadius: '50%', flex: 'none',
              background: ollama?.running ? 'var(--acc)' : 'var(--bad)',
            }}
          />
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-bold">
              Ollama {ollama?.running ? `运行中 · v${ollama.version || '?'}` : '未运行'}
              {ollama?.running && (
                <span className="ml-2 text-[11px] font-normal" style={{ color: 'var(--dim)' }}>
                  {ollama.host} · {ollama.models_count} 个本地模型
                </span>
              )}
            </div>
            <div className="text-[11px] mt-1" style={{ color: 'var(--dim)' }}>
              {ollama?.running
                ? local?.error || '本地开源模型运行时就绪，可在下方下载 / 选用模型'
                : ollama?.error || '—'}
            </div>
          </div>
          {!ollama?.running && (
            <div className="text-[11px] max-w-[320px]" style={{ color: 'var(--dim)' }}>
              {ollama?.install_hint}
            </div>
          )}
          <div className="text-right flex-none">
            <div className="label">歌词引擎</div>
            <div className="text-[12px] font-bold mt-1" style={{ color: 'var(--acc)' }}>
              {runtime?.engine || '…'}
            </div>
            <div className="label mt-2">歌曲引擎</div>
            <div className="text-[12px] font-bold mt-1" style={{ color: 'var(--acc)' }}>
              {runtime?.song_engine || '…'}
            </div>
          </div>
        </div>

        {/* 歌曲生成引擎通道（V1.3/V1.4） */}
        <div className="mt-8">
          <div className="label mb-3">歌曲生成引擎通道</div>
          <div className="grid grid-cols-2 gap-3">
            {MUSIC_BACKENDS.map((b) => {
              const on = musicBackend === b.value
              return (
                <div
                  key={b.value}
                  className={`card p-4 cursor-pointer transition-all ${on ? '' : 'opacity-70 hover:opacity-100'}`}
                  style={on ? { borderColor: 'var(--acc)' } : undefined}
                  onClick={() => {
                    if (b.value === 'api' && !musicBase && settings?.music_backend !== 'api') {
                      toast('请先在下方完成外部歌曲 API 配置')
                      return
                    }
                    if (b.value === 'replicate' && settings?.music_backend !== 'replicate'
                        && !settings?.replicate_api_token.has_key) {
                      toast('请先在下方目录区保存 Replicate API Token')
                      return
                    }
                    if ((b.value === 'musicgen_local' || b.value === 'acestep_local')
                        && !settings?.music_model) {
                      toast('请先在下方目录选择支持本机运行的模型')
                      return
                    }
                    setMusicBackend(b.value)
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-bold">{b.title}</span>
                    <span
                      className="text-[10px] font-bold px-1.5 py-0.5"
                      style={{
                        background: on ? 'var(--acc)' : 'var(--bg3)',
                        color: on ? '#000' : 'var(--dim)',
                      }}
                    >
                      {on ? '使用中' : '选择'}
                    </span>
                  </div>
                  <div className="text-[11px] mt-2" style={{ color: 'var(--dim)' }}>{b.desc}</div>
                </div>
              )
            })}
          </div>
          {musicBackend !== settings?.music_backend && (
            <div className="mt-3 flex items-center gap-3">
              <button className="btn btn-acc" disabled={musicSaving} onClick={() => void saveMusic(musicBackend)}>
                {musicSaving ? '切换中…' : '应用切换'}
              </button>
              <span className="text-[11px]" style={{ color: 'var(--dim)' }}>
                切换立即生效，影响工作台的整曲生成（歌词助手不受影响）
              </span>
            </div>
          )}

          {/* 外部歌曲 API 配置 */}
          <div className="card mt-3 p-5">
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
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <div className="label mb-1">BASE URL（Suno 兼容网关根，自动补 /api/v1）</div>
                <input
                  className="w-full px-3 py-2 text-[12px]"
                  style={{
                    background: 'var(--bg)', border: '1px solid var(--line)',
                    color: 'var(--txt)', outline: 'none',
                  }}
                  placeholder="https://api.goapi.ai/suno 或 http://localhost:3000"
                  value={musicBase}
                  onChange={(e) => setMusicBase(e.target.value)}
                />
              </div>
              <div>
                <div className="label mb-1">
                  API KEY{' '}
                  {settings?.music_api_key.has_key && (
                    <span style={{ color: 'var(--dim)' }}>
                      （已保存 ····{settings.music_api_key.key_tail}，留空即沿用）
                    </span>
                  )}
                </div>
                <input
                  className="w-full px-3 py-2 text-[12px]"
                  type="password"
                  style={{
                    background: 'var(--bg)', border: '1px solid var(--line)',
                    color: 'var(--txt)', outline: 'none',
                  }}
                  placeholder={settings?.music_api_key.has_key ? '••••••••（不变）' : 'sk-…'}
                  value={musicKey}
                  onChange={(e) => setMusicKey(e.target.value)}
                />
              </div>
              <div>
                <div className="label mb-1">MODEL（可选，网关区分模型时填写）</div>
                <input
                  className="w-full px-3 py-2 text-[12px]"
                  style={{
                    background: 'var(--bg)', border: '1px solid var(--line)',
                    color: 'var(--txt)', outline: 'none',
                  }}
                  placeholder="如 V3 / V4 / V4_5，留空用网关默认"
                  value={musicModel}
                  onChange={(e) => setMusicModel(e.target.value)}
                />
              </div>
            </div>
            <div className="flex items-center gap-3 mt-4">
              <button className="btn" disabled={musicTesting} onClick={() => void runMusicTest()}>
                {musicTesting ? '测试中…' : '测试连接'}
              </button>
              <button className="btn btn-acc" disabled={musicSaving} onClick={() => void saveMusic('api')}>
                {musicSaving ? '保存中…' : '保存并启用'}
              </button>
              {musicTestResult && (
                <span
                  className="text-[11px]"
                  style={{ color: musicTestResult.ok ? 'var(--acc)' : 'var(--bad)' }}
                >
                  {musicTestResult.ok ? '✓' : '✕'} {musicTestResult.message}
                </span>
              )}
            </div>
            <div className="text-[10px] mt-3 leading-relaxed" style={{ color: 'var(--dim)' }}>
              采用社区通行的 Suno 兼容协议（POST /api/v1/generate + GET /api/v1/get），
              GoAPI / suno-api 自建网关及各类中转站均可直连。外部候选为整曲 mp3（含人声演唱），
              不含分轨/MIDI；派生编辑与 WAV/分轨/MIDI 导出仅支持本地引擎候选，MP3 导出可用。
            </div>
          </div>
        </div>

        {/* 开源歌曲模型目录（V1.4：按外部测评排序 + 推荐） */}
        <div className="mt-8">
          <div className="label mb-3">开源歌曲模型目录（按外部测评排序）</div>

          {/* Replicate Token 配置 */}
          <div className="card p-5">
            <div className="grid grid-cols-2 gap-3 items-end">
              <div>
                <div className="label mb-1">
                  REPLICATE API TOKEN{' '}
                  {settings?.replicate_api_token.has_key && (
                    <span style={{ color: 'var(--dim)' }}>
                      （已保存 ····{settings.replicate_api_token.key_tail}，留空即沿用）
                    </span>
                  )}
                </div>
                <input
                  className="w-full px-3 py-2 text-[12px]"
                  type="password"
                  style={{
                    background: 'var(--bg)', border: '1px solid var(--line)',
                    color: 'var(--txt)', outline: 'none',
                  }}
                  placeholder={settings?.replicate_api_token.has_key ? '••••••••（不变）' : 'r8_…（replicate.com 账户获取）'}
                  value={replicateKey}
                  onChange={(e) => setReplicateKey(e.target.value)}
                />
              </div>
              <div className="flex items-center gap-2">
                <button className="btn" disabled={replicateTesting} onClick={() => void runReplicateTest()}>
                  {replicateTesting ? '测试中…' : '测试 Token'}
                </button>
                <button className="btn btn-acc" disabled={replicateSaving} onClick={() => void saveReplicate()}>
                  {replicateSaving ? '保存中…' : '保存 Token'}
                </button>
                {replicateTestResult && (
                  <span
                    className="text-[11px] truncate"
                    style={{ color: replicateTestResult.ok ? 'var(--acc)' : 'var(--bad)' }}
                  >
                    {replicateTestResult.ok ? '✓' : '✕'} {replicateTestResult.message}
                  </span>
                )}
              </div>
            </div>
            {catalog && !catalog.machine.musicgen_deps_installed && (
              <div className="text-[11px] mt-3 leading-relaxed" style={{ color: 'var(--dim)' }}>
                MusicGen：{catalog.machine.install_hint}
              </div>
            )}
            {catalog && !catalog.machine.acestep_deps_installed && (
              <div className="text-[11px] mt-2 leading-relaxed" style={{ color: 'var(--dim)' }}>
                ACE-Step：{catalog.machine.acestep_install_hint}
              </div>
            )}
          </div>

          {/* 目录列表 */}
          <div className="mt-3 space-y-3">
            {(catalog?.models || []).map((m) => {
              const st = localStatusText(m)
              const localChannel = localChannelOf(m)
              return (
                <div key={m.id} className="card p-4" style={m.selected ? { borderColor: 'var(--acc)' } : undefined}>
                  <div className="flex items-start gap-3 flex-wrap">
                    <span
                      className="text-[10px] font-bold px-1.5 py-1 num flex-none"
                      style={{ background: 'var(--bg3)', color: 'var(--muted)' }}
                      title="外部测评参考分排名"
                    >
                      #{m.rank}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[13px] font-bold">{m.name}</span>
                        <span
                          className="text-[9px] font-bold px-1.5 py-0.5 num"
                          style={{ background: 'var(--acc-dim)', color: 'var(--acc)' }}
                          title={`来源：${m.benchmark.source}\n${m.benchmark.notes}`}
                        >
                          测评 {m.benchmark.score.toFixed(1)}
                        </span>
                        {m.recommended && (
                          <span
                            className="text-[9px] font-bold px-1.5 py-0.5"
                            style={{ background: 'var(--acc)', color: '#000' }}
                            title={m.recommend_reason}
                          >
                            推荐
                          </span>
                        )}
                        {m.selected && (
                          <span className="text-[9px] font-bold px-1.5 py-0.5" style={{ background: 'var(--acc)', color: '#000' }}>
                            使用中
                          </span>
                        )}
                        <span className="text-[10px]" style={{ color: st.color }}>{st.text}</span>
                      </div>
                      <div className="text-[11px] mt-1" style={{ color: 'var(--dim)' }}>
                        {m.vendor} · {m.params} · {m.license}
                      </div>
                      <div className="flex gap-1.5 mt-2 flex-wrap">
                        <span className="text-[10px] px-1.5 py-0.5" style={{ background: 'var(--bg3)', color: 'var(--muted)' }}>
                          {m.capabilities.vocals ? '人声+歌词成曲' : '纯器乐'}
                        </span>
                        <span className="text-[10px] px-1.5 py-0.5" style={{ background: 'var(--bg3)', color: 'var(--muted)' }}>
                          ≤{m.capabilities.max_duration_sec}s
                        </span>
                        <span className="text-[10px] px-1.5 py-0.5" style={{ background: 'var(--bg3)', color: 'var(--muted)' }}>
                          {m.capabilities.languages}
                        </span>
                        <span className="text-[10px] px-1.5 py-0.5" style={{ background: 'var(--bg3)', color: 'var(--muted)' }}>
                          {localChannel ? '本机/托管' : 'Replicate 托管'}
                        </span>
                      </div>
                      <div className="text-[10px] mt-1.5 leading-relaxed" style={{ color: 'var(--dim)' }}>
                        {m.benchmark.notes}{m.local_note ? ` · ${m.local_note}` : ''}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-none flex-wrap">
                      {m.channels.includes('replicate') && (
                        <button
                          className="btn !py-1 !px-2.5 text-[11px]"
                          disabled={catalogBusy || m.selected}
                          onClick={() => void useCatalogModel(m, 'replicate')}
                        >
                          云端使用
                        </button>
                      )}
                      {localChannel && (
                        <>
                          <button
                            className="btn !py-1 !px-2.5 text-[11px]"
                            disabled={catalogBusy || m.selected}
                            onClick={() => void useCatalogModel(m, localChannel)}
                          >
                            本机使用
                          </button>
                          {m.local_status !== 'ready' ? (
                            <button
                              className="btn btn-acc !py-1 !px-2.5 text-[11px]"
                              disabled={catalogBusy || !!activeOp}
                              onClick={() => void downloadMusicModel(m)}
                            >
                              下载 ≈{m.local_size_mb}MB
                            </button>
                          ) : (
                            <button
                              className="btn !py-1 !px-2.5 text-[11px]"
                              style={{ color: 'var(--bad)' }}
                              disabled={catalogBusy}
                              onClick={() => void removeMusicModel(m)}
                            >
                              删除
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                  {m.channels.includes('replicate') && (
                    <div className="flex items-center gap-2 mt-3" title="Replicate 模型 slug（社区托管变动时可覆盖）">
                      <span className="text-[10px] flex-none" style={{ color: 'var(--dim)' }}>slug</span>
                      <input
                        className="flex-1 px-2 py-1 text-[11px]"
                        style={{
                          background: 'var(--bg)', border: '1px solid var(--line)',
                          color: 'var(--txt)', outline: 'none',
                        }}
                        placeholder={m.replicate_slug_default || 'owner/name（replicate.com 查询后填写）'}
                        value={slugEdits[m.id] ?? ''}
                        onChange={(e) => setSlugEdits((p) => ({ ...p, [m.id]: e.target.value }))}
                      />
                      {m.replicate_slug_overridden && (
                        <span className="text-[10px] flex-none" style={{ color: 'var(--dim)' }}>已覆盖</span>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          <div className="flex items-center gap-3 mt-3">
            <button className="btn" disabled={catalogBusy} onClick={() => void saveSlugs()}>
              保存 slug 覆盖
            </button>
            <span className="text-[10px] flex-1" style={{ color: 'var(--dim)' }}>
              {catalog?.disclaimer}
            </span>
          </div>
        </div>

        {/* 通道选择 */}
        <div className="mt-8">
          <div className="label mb-3">歌词引擎通道</div>
          <div className="grid grid-cols-3 gap-3">
            {BACKENDS.map((b) => {
              const on = backend === b.value
              return (
                <div
                  key={b.value}
                  className={`card p-4 cursor-pointer transition-all ${on ? '' : 'opacity-70 hover:opacity-100'}`}
                  style={on ? { borderColor: 'var(--acc)' } : undefined}
                  onClick={() => {
                    if (b.value === 'ollama' && !local?.models.length) {
                      toast('本机还没有本地模型，请先在下方下载')
                      return
                    }
                    setBackend(b.value)
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-bold">{b.title}</span>
                    <span
                      className="text-[10px] font-bold px-1.5 py-0.5"
                      style={{
                        background: on ? 'var(--acc)' : 'var(--bg3)',
                        color: on ? '#000' : 'var(--dim)',
                      }}
                    >
                      {on ? '使用中' : '选择'}
                    </span>
                  </div>
                  <div className="text-[11px] mt-2" style={{ color: 'var(--dim)' }}>{b.desc}</div>
                  {b.value === 'ollama' && local && local.models.length > 0 && (
                    <select
                      className="w-full mt-3 text-[12px] px-2 py-1.5"
                      style={{
                        background: 'var(--bg)', border: '1px solid var(--line)',
                        color: 'var(--txt)', outline: 'none',
                      }}
                      value={pickedModel}
                      onChange={(e) => {
                        setPickedModel(e.target.value)
                        if (backend === 'ollama') void saveBackend('ollama', { ollama_model: e.target.value })
                      }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {local.models.map((m) => (
                        <option key={m.name} value={m.name}>
                          {m.name}（{m.parameter_size || '?'} · {fmtSize(m.size_bytes)}）
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )
            })}
          </div>
          {backend !== settings?.lyrics_backend && (
            <div className="mt-3 flex items-center gap-3">
              <button className="btn btn-acc" disabled={saving} onClick={() => void saveBackend(backend)}>
                {saving ? '切换中…' : '应用切换'}
              </button>
              <span className="text-[11px]" style={{ color: 'var(--dim)' }}>
                切换立即生效，影响歌词助手的生成 / 润色
              </span>
            </div>
          )}
        </div>

        {/* 本地开源模型 */}
        <div className="mt-8">
          <div className="label mb-3">本地开源模型（Ollama）</div>
          <div className="card">
            {local && local.models.length > 0 ? (
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="label" style={{ color: 'var(--dim)' }}>
                    <th className="text-left px-4 py-2 font-normal">模型</th>
                    <th className="text-left px-4 py-2 font-normal">参数 / 量化</th>
                    <th className="text-left px-4 py-2 font-normal">大小</th>
                    <th className="text-right px-4 py-2 font-normal">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {local.models.map((m) => (
                    <tr key={m.name} className="rule-t">
                      <td className="px-4 py-2.5">
                        <span className="font-bold">{m.name}</span>
                        {settings?.lyrics_backend === 'ollama' && local.selected === m.name && (
                          <span
                            className="ml-2 text-[9px] font-bold px-1.5 py-0.5"
                            style={{ background: 'var(--acc)', color: '#000' }}
                          >
                            引擎使用中
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5" style={{ color: 'var(--muted)' }}>
                        {m.parameter_size || '—'} · {m.quantization || '—'}
                      </td>
                      <td className="px-4 py-2.5 num" style={{ color: 'var(--muted)' }}>
                        {fmtSize(m.size_bytes)}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <button
                          className="btn !py-1 !px-2.5 text-[11px] mr-2"
                          disabled={settings?.lyrics_backend === 'ollama' && local.selected === m.name}
                          onClick={() => {
                            setPickedModel(m.name)
                            void saveBackend('ollama', { ollama_model: m.name })
                          }}
                        >
                          设为引擎
                        </button>
                        <button
                          className="btn !py-1 !px-2.5 text-[11px]"
                          style={{ color: 'var(--bad)' }}
                          onClick={() => void removeModel(m.name)}
                        >
                          删除
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="px-4 py-6 text-[12px]" style={{ color: 'var(--dim)' }}>
                {local?.error || '暂无本地模型，从下方推荐清单下载一个开始使用'}
              </div>
            )}
          </div>

          {/* 下载区 */}
          <div className="card mt-3 p-4">
            <div className="label mb-2">下载新模型</div>
            <div className="flex flex-wrap gap-2 mb-3">
              {(local?.recommended || presets?.recommended_models || []).map((r) => (
                <span
                  key={r.tag}
                  className="chip"
                  title={`${r.note} · 约 ${r.size_mb}MB`}
                  onClick={() => setPullTag(r.tag)}
                >
                  {r.tag} · ≈{r.size_mb}MB
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                className="flex-1 px-3 py-2 text-[12px]"
                style={{
                  background: 'var(--bg)', border: '1px solid var(--line)',
                  color: 'var(--txt)', outline: 'none',
                }}
                placeholder="或输入自定义 tag，如 qwen3.5:1.7b"
                value={pullTag}
                onChange={(e) => setPullTag(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void startPull(pullTag)
                }}
              />
              <button className="btn btn-acc" disabled={pulling || !!activeOp} onClick={() => void startPull(pullTag)}>
                {pulling || activeOp ? '下载中…' : '下载'}
              </button>
            </div>
            <div className="text-[10px] mt-2" style={{ color: 'var(--dim)' }}>
              从 Ollama 公共仓库拉取（ollama.com/library）；下载进度实时显示，可离开本页
            </div>
            {activeOp && (
              <div className="mt-3">
                <div className="flex items-center justify-between text-[11px] mb-1">
                  <span className="font-bold">{activeOp.target}</span>
                  <span className="num" style={{ color: 'var(--acc)' }}>
                    {activeOp.progress}% · {activeOp.message}
                  </span>
                </div>
                <div className="h-[4px]" style={{ background: 'var(--bg3)' }}>
                  <div
                    className="h-full transition-all"
                    style={{ width: `${activeOp.progress}%`, background: 'var(--acc)' }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* 操作记录 */}
          {ops.length > 0 && (
            <div className="card mt-3 p-4">
              <div className="label mb-2">最近操作</div>
              {ops.map((op) => (
                <div key={op.id} className="flex items-center gap-3 text-[11px] py-1">
                  <span style={{ color: 'var(--dim)' }} className="num">
                    {formatDateTime(op.created_at)}
                  </span>
                  <span className="font-bold">{OP_TYPE_LABEL[op.op_type] ?? op.op_type}</span>
                  <span>{op.target}</span>
                  <span
                    className="flex-1"
                    style={{
                      color: op.status === 'succeeded'
                        ? 'var(--acc)'
                        : op.status === 'failed' ? 'var(--bad)' : 'var(--dim)',
                    }}
                  >
                    {op.status === 'succeeded' ? '成功' : op.status === 'failed'
                      ? `失败：${op.error_message || '未知错误'}` : `${op.progress}% ${op.message}`}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 外部 API */}
        <div className="mt-8 mb-10">
          <div className="label mb-3">外部 API（OpenAI 兼容）</div>
          <div className="card p-5">
            <div className="flex flex-wrap gap-2 mb-4">
              {(presets?.external_presets || []).map((p) => (
                <span
                  key={p.vendor}
                  className="chip"
                  title={`${p.base_url} · 推荐 ${p.model_hint}`}
                  onClick={() => {
                    setExtBase(p.base_url)
                    if (!extModel) setExtModel(p.model_hint.split('（')[0])
                  }}
                >
                  {p.vendor}
                </span>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <div className="label mb-1">BASE URL</div>
                <input
                  className="w-full px-3 py-2 text-[12px]"
                  style={{
                    background: 'var(--bg)', border: '1px solid var(--line)',
                    color: 'var(--txt)', outline: 'none',
                  }}
                  placeholder="https://open.bigmodel.cn/api/paas/v4"
                  value={extBase}
                  onChange={(e) => setExtBase(e.target.value)}
                />
              </div>
              <div>
                <div className="label mb-1">
                  API KEY{' '}
                  {settings?.external_api_key.has_key && (
                    <span style={{ color: 'var(--dim)' }}>
                      （已保存 ····{settings.external_api_key.key_tail}，留空即沿用）
                    </span>
                  )}
                </div>
                <input
                  className="w-full px-3 py-2 text-[12px]"
                  type="password"
                  style={{
                    background: 'var(--bg)', border: '1px solid var(--line)',
                    color: 'var(--txt)', outline: 'none',
                  }}
                  placeholder={settings?.external_api_key.has_key ? '••••••••（不变）' : 'sk-…'}
                  value={extKey}
                  onChange={(e) => setExtKey(e.target.value)}
                />
              </div>
              <div>
                <div className="label mb-1">MODEL</div>
                <input
                  className="w-full px-3 py-2 text-[12px]"
                  style={{
                    background: 'var(--bg)', border: '1px solid var(--line)',
                    color: 'var(--txt)', outline: 'none',
                  }}
                  placeholder="glm-4-flash / deepseek-chat / gpt-4o-mini"
                  value={extModel}
                  onChange={(e) => setExtModel(e.target.value)}
                />
              </div>
            </div>
            <div className="flex items-center gap-3 mt-4">
              <button className="btn" disabled={testing} onClick={() => void runTest()}>
                {testing ? '测试中…' : '测试连接'}
              </button>
              <button className="btn btn-acc" disabled={saving} onClick={() => void saveExternal()}>
                {saving ? '保存中…' : '保存并启用'}
              </button>
              {testResult && (
                <span className="text-[11px]" style={{ color: testResult.ok ? 'var(--acc)' : 'var(--bad)' }}>
                  {testResult.ok ? '✓' : '✕'} {testResult.message}
                  {testResult.sample ? `（回声：${testResult.sample}）` : ''}
                </span>
              )}
            </div>
            <div className="text-[10px] mt-3" style={{ color: 'var(--dim)' }}>
              标准 chat/completions 协议：智谱 GLM、DeepSeek、OpenAI、Moonshot、通义等均可直连；
              也兼容本地网关（如 Ollama 的 http://localhost:11434/v1，Key 可任意填）。
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
