import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
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
  deployAceStep,
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
import { t, useT, type TranslationKey } from '../i18n'

function fmtSize(bytes: number): string {
  if (!bytes) return '-'
  const gb = bytes / 1024 ** 3
  if (gb >= 1) return `${gb.toFixed(1)} GB`
  return `${Math.round(bytes / 1024 ** 2)} MB`
}

/** 通道元数据（按 id 查找；分组渲染见 LYRICS_GROUPS / MUSIC_GROUPS） */
const BACKENDS: Record<LyricsBackend, { title: TranslationKey; desc: TranslationKey }> = {
  localsynth: { title: 'models.backend.localsynth.title', desc: 'models.backend.localsynth.desc' },
  ollama: { title: 'models.backend.ollama.title', desc: 'models.backend.ollama.desc' },
  openai_compat: { title: 'models.backend.openai_compat.title', desc: 'models.backend.openai_compat.desc' },
}

const MUSIC_BACKENDS: Record<MusicBackend, { title: TranslationKey; desc: TranslationKey }> = {
  localsynth: { title: 'models.mbackend.localsynth.title', desc: 'models.mbackend.localsynth.desc' },
  acestep_local: { title: 'models.mbackend.acestep_local.title', desc: 'models.mbackend.acestep_local.desc' },
  mmax_local: { title: 'models.mbackend.mmax_local.title', desc: 'models.mbackend.mmax_local.desc' },
  songgen_local: { title: 'models.mbackend.songgen_local.title', desc: 'models.mbackend.songgen_local.desc' },
  replicate: { title: 'models.mbackend.replicate.title', desc: 'models.mbackend.replicate.desc' },
  api: { title: 'models.mbackend.api.title', desc: 'models.mbackend.api.desc' },
  musicgen_local: { title: 'models.mbackend.musicgen_local.title', desc: 'models.mbackend.musicgen_local.desc' },
}

/** 歌词引擎通道分组：推荐真实模型通道在前，离线兜底（非 AI）降级殿后 */
const LYRICS_GROUPS: { labelKey: TranslationKey; items: LyricsBackend[]; fallback?: boolean }[] = [
  { labelKey: 'models.group.recommended', items: ['openai_compat', 'ollama'] },
  { labelKey: 'models.group.fallback', items: ['localsynth'], fallback: true },
]

/** 歌曲引擎通道分组：云端 / 本机 GPU / 自托管服务 / 离线兜底 */
const MUSIC_GROUPS: { labelKey: TranslationKey; items: MusicBackend[]; fallback?: boolean }[] = [
  { labelKey: 'models.group.cloud', items: ['api', 'replicate'] },
  { labelKey: 'models.group.localGpu', items: ['acestep_local', 'musicgen_local'] },
  { labelKey: 'models.group.selfhosted', items: ['mmax_local', 'songgen_local'] },
  { labelKey: 'models.group.fallback', items: ['localsynth'], fallback: true },
]

/** 左侧分类导航（锚点 + scrollspy 高亮） */
const SECTIONS: { id: string; labelKey: TranslationKey }[] = [
  { id: 'mc-overview', labelKey: 'models.nav.overview' },
  { id: 'mc-components', labelKey: 'models.nav.components' },
  { id: 'mc-lyrics', labelKey: 'models.nav.lyrics' },
  { id: 'mc-music', labelKey: 'models.nav.music' },
  { id: 'mc-catalog', labelKey: 'models.nav.catalog' },
  { id: 'mc-library', labelKey: 'models.nav.library' },
  { id: 'mc-ops', labelKey: 'models.nav.ops' },
]

/** 支持本机/自托管运行的通道（目录按钮/状态按此泛化渲染） */
const LOCAL_CHANNELS: MusicBackend[] = ['acestep_local', 'musicgen_local', 'mmax_local', 'songgen_local']
/** 下载型本机通道（权重经模型中心下载）；其余本机通道为自托管服务型（端点可配） */
const DOWNLOAD_CHANNELS: MusicBackend[] = ['acestep_local', 'musicgen_local']
const localChannelOf = (m: MusicCatalogModel): MusicBackend | undefined =>
  m.channels.find((c) => LOCAL_CHANNELS.includes(c))

const OP_TYPE_LABEL: Record<ModelOpInfo['op_type'], TranslationKey> = {
  pull: 'common.download', delete: 'common.delete', music_pull: 'common.download',
  music_delete: 'common.delete', acestep_deploy: 'models.comp.deploying',
}

/** 目录模型的本机状态文案（t 为模块级翻译函数；本组件经 useT 订阅语言变化后重渲染） */
function localStatusText(m: MusicCatalogModel): { text: string; cls: string } {
  if (m.local_status === 'ready') return { text: t('models.status.ready'), cls: 'text-acc' }
  if (m.local_status === 'deps_missing') return { text: t('models.status.depsMissing'), cls: 'text-bad' }
  if (m.local_status === 'not_downloaded') return { text: t('models.status.notDownloaded'), cls: 'text-dim' }
  if (m.local_status === 'not_running') return { text: t('models.status.notRunning'), cls: 'text-bad' }
  return { text: t('models.status.hostedOnly'), cls: 'text-dim' }
}

/** 模型中心（契约 §5.8）：左侧分类导航 + 概览/歌词引擎/歌曲引擎/开源目录/本地模型库/操作记录 */
export default function ModelCenterView() {
  const confirm = useConfirmStore((s) => s.confirm)
  const t = useT()
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
  const [hostEdits, setHostEdits] = useState<Record<string, string>>({})
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

  const [ollamaHostEdit, setOllamaHostEdit] = useState('')
  const [hostSaving, setHostSaving] = useState(false)

  const [activeSection, setActiveSection] = useState(SECTIONS[0].id)
  const scrollRef = useRef<HTMLDivElement>(null)
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
    setHostEdits(st.local_service_hosts || {})
    setOllamaHostEdit(st.ollama_host)
  }, [])

  useEffect(() => {
    void refreshAll().catch(() => {
      /* 拦截器已 toast */
    })
  }, [refreshAll])

  // scrollspy：分区进入滚动视口上部区域时高亮侧边栏对应项（SSR/测试环境无 IO，防御跳过）
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return
    const root = scrollRef.current
    if (!root) return
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting && e.target.id) setActiveSection(e.target.id)
        }
      },
      { root, rootMargin: '-8% 0px -80% 0px' },
    )
    for (const s of SECTIONS) {
      const el = document.getElementById(s.id)
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [])

  const jump = (id: string) => {
    setActiveSection(id)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

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

  // ACE-Step 组件部署在桌面首启后台自动发起时（v0.16.3 默认安装即部署）：
  // 进入模型中心即接管轮询，卡片进度实时化
  useEffect(() => {
    const dop = catalog?.machine.acestep_deploy_op
    if (!activeOp && dop && (dop.status === 'queued' || dop.status === 'running')) {
      setActiveOp(dop)
    }
  }, [catalog, activeOp])

  const startAceDeploy = async () => {
    setCatalogBusy(true)
    try {
      const op = await deployAceStep()
      setActiveOp(op)
      toast(t('models.comp.deployStarted'))
    } catch {
      /* 拦截器已 toast（409=已有部署/下载进行中）；刷新以接管展示在跑操作 */
      void refreshAll().catch(() => {})
    } finally {
      setCatalogBusy(false)
    }
  }

  const saveBackend = async (target: LyricsBackend, extra: Record<string, string> = {}) => {
    if (target === 'ollama' && !pickedModel && !extra.ollama_model) {
      toast(t('models.lyrics.needModel'))
      return
    }
    if (target === 'openai_compat' && !(extBase || extra.external_base_url)) {
      toast(t('models.lyrics.needExternal'))
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
      toast(t('models.lyrics.switched', { engine: rt.engine }))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setSaving(false)
    }
  }

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

  const startPull = async (tag: string) => {
    const model = tag.trim()
    if (!model) {
      toast(t('models.pull.needTag'))
      return
    }
    setPulling(true)
    try {
      const op = await pullModel(model)
      setActiveOp(op)
      setPullTag('')
      toast(t('models.pull.started', { model }))
    } catch {
      /* 拦截器已 toast（重复下载 / 格式错误等） */
    } finally {
      setPulling(false)
    }
  }

  const removeModel = async (name: string) => {
    const ok = await confirm({
      title: t('models.del.title', { name }),
      description: t('models.del.desc'),
      confirmText: t('common.delete'),
      danger: true,
    })
    if (!ok) return
    try {
      const op = await deleteModel(name)
      if (op.status === 'succeeded') toast(t('models.del.done', { name }))
      else toast(op.error_message || t('models.del.failed'), 'warn')
      await refreshAll()
    } catch {
      /* 拦截器已 toast */
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

  const downloadMusicModel = async (m: MusicCatalogModel) => {
    setCatalogBusy(true)
    try {
      const op = await pullMusicModel(m.id)
      setActiveOp(op)
      toast(t('models.music.pullStarted', { name: m.name, size: m.local_size_mb }))
    } catch {
      /* 拦截器已 toast */
    } finally {
      setCatalogBusy(false)
    }
  }

  const removeMusicModel = async (m: MusicCatalogModel) => {
    const ok = await confirm({
      title: t('models.musicDel.title', { name: m.name }),
      description: t('models.musicDel.desc'),
      confirmText: t('common.delete'),
      danger: true,
    })
    if (!ok) return
    try {
      const op = await deleteMusicModel(m.id)
      if (op.status === 'succeeded') toast(t('models.del.done', { name: m.name }))
      else toast(op.error_message || t('models.del.failed'), 'warn')
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

  const ollama = runtime?.ollama
  // 生产就绪检查：任一引擎仍在离线兜底（非 AI 规则/算法引擎）即提示配置真实模型通道
  const lyricsReady = !!settings && settings.lyrics_backend !== 'localsynth'
  const songReady = !!settings && settings.music_backend !== 'localsynth'

  // ---- 本地组件中心（v0.16.0）：数据切片与行渲染 ----
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

  /** 通道卡通用渲染（fallback 组弱化样式 + 「非 AI · 兜底」徽章） */
  const renderChannelCard = (
    title: TranslationKey, desc: TranslationKey,
    on: boolean, onClick: () => void, fallback = false, children?: React.ReactNode,
  ) => (
    <div
      className={`card p-4 cursor-pointer transition-colors ${on ? '' : 'opacity-70 hover:opacity-100'}`}
      style={{
        // .card 未分层、优先级高于 utility：选中态描边/虚线只能用内联样式覆盖
        ...(on ? { borderColor: 'var(--acc)' } : {}),
        ...(fallback && !on ? { borderStyle: 'dashed' } : {}),
      }}
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <span className="text-base font-bold">{t(title)}</span>
        <span className="flex items-center gap-1.5">
          {fallback && <span className="badge badge-warn">{t('models.fallbackBadge')}</span>}
          <span className={`badge ${on ? 'badge-solid' : ''}`}>
            {on ? t('models.chan.inUse') : t('models.chan.select')}
          </span>
        </span>
      </div>
      <div className="text-xs mt-2 text-dim">{t(desc)}</div>
      {children}
    </div>
  )

  /** 表单控件 token 类（与 index.css 表单基础规则同值，显式声明防漂移） */
  const inputCls = 'bg-bg border border-line text-txt outline-none'

  return (
    <div className="view h-full overflow-y-auto" ref={scrollRef}>
      <div className="max-w-[1240px] mx-auto px-8 py-8">
        <div className="label">{t('models.label')}</div>
        <h1 className="text-3xl font-extrabold tracking-tight mt-2">{t('models.title')}</h1>
        <p className="text-sm mt-2 text-dim">
          {t('models.intro')}
        </p>

        <div className="flex items-start gap-8 mt-6">
          {/* 左侧分类导航 */}
          <aside className="w-[168px] flex-none sticky top-6 hidden lg:block">
            <div className="py-1">
              {SECTIONS.map((s) => {
                const active = activeSection === s.id
                return (
                  <button
                    key={s.id}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors flex items-center gap-2 border-l-2 ${
                      active ? 'text-acc font-bold bg-bg-2 border-acc' : 'text-muted font-normal border-transparent'
                    }`}
                    onClick={() => jump(s.id)}
                  >
                    {t(s.labelKey)}
                  </button>
                )
              })}
            </div>
          </aside>

          <div className="flex-1 min-w-0">
            {/* ============ 概览 ============ */}
            <section id="mc-overview" className="scroll-mt-4">
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
                  {([
                    { ready: lyricsReady, engineLabel: 'models.runtime.lyricsEngine', okKey: 'models.overview.lyricsOk', fbKey: 'models.overview.lyricsFallback', target: 'mc-lyrics' },
                    { ready: songReady, engineLabel: 'models.runtime.songEngine', okKey: 'models.overview.songOk', fbKey: 'models.overview.songFallback', target: 'mc-music' },
                  ] as const).map((row) => (
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

            {/* ============ 歌词引擎 ============ */}

            {/* ============ 本地组件中心（v0.16.0 桌面按需下载，方案 §3.2） ============ */}
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

            <section id="mc-lyrics" className="mt-10 scroll-mt-4">
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
                      <Fragment key={value}>
                        {renderChannelCard(
                          BACKENDS[value].title, BACKENDS[value].desc,
                          backend === value, () => {
                            if (value === 'ollama' && !local?.models.length) {
                              toast(t('models.lyrics.noLocal'))
                              return
                            }
                            setBackend(value)
                          }, g.fallback,
                          value === 'ollama' && local && local.models.length > 0 ? (
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
                          ) : undefined,
                        )}
                      </Fragment>
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

            {/* ============ 歌曲引擎 ============ */}
            <section id="mc-music" className="mt-10 scroll-mt-4">
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
                      <Fragment key={value}>
                        {renderChannelCard(
                          MUSIC_BACKENDS[value].title, MUSIC_BACKENDS[value].desc,
                          musicBackend === value, () => {
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
                          }, g.fallback,
                        )}
                      </Fragment>
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

            {/* ============ 开源歌曲模型目录 ============ */}
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
                            onChange={(e) => setSlugEdits((p) => ({ ...p, [m.id]: e.target.value }))}
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
                              onChange={(e) => setHostEdits((p) => ({ ...p, [localChannel]: e.target.value }))}
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

            {/* ============ 本地模型库 ============ */}
            <section id="mc-library" className="mt-10 scroll-mt-4">
              <div className="label mb-3">{t('models.local.title')}</div>
              <div className="card">
                {local && local.models.length > 0 ? (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="label">
                        <th className="text-left px-4 py-2 font-normal">{t('models.local.col.model')}</th>
                        <th className="text-left px-4 py-2 font-normal">{t('models.local.col.params')}</th>
                        <th className="text-left px-4 py-2 font-normal">{t('models.local.col.size')}</th>
                        <th className="text-right px-4 py-2 font-normal">{t('models.local.col.actions')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {local.models.map((m) => (
                        <tr key={m.name} className="rule-t">
                          <td className="px-4 py-2.5">
                            <span className="font-bold">{m.name}</span>
                            {settings?.lyrics_backend === 'ollama' && local.selected === m.name && (
                              <span className="badge badge-solid ml-2">
                                {t('models.local.engineInUse')}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-2.5 text-muted">
                            {m.parameter_size || '—'} · {m.quantization || '—'}
                          </td>
                          <td className="px-4 py-2.5 num text-muted">
                            {fmtSize(m.size_bytes)}
                          </td>
                          <td className="px-4 py-2.5 text-right">
                            <button
                              className="btn btn-sm mr-2"
                              disabled={settings?.lyrics_backend === 'ollama' && local.selected === m.name}
                              onClick={() => {
                                setPickedModel(m.name)
                                void saveBackend('ollama', { ollama_model: m.name })
                              }}
                            >
                              {t('models.local.setEngine')}
                            </button>
                            <button
                              className="btn btn-sm"
                              style={{ color: 'var(--bad)' }}
                              onClick={() => void removeModel(m.name)}
                            >
                              {t('common.delete')}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="px-4 py-6 text-sm text-dim">
                    {local?.error || t('models.local.empty')}
                  </div>
                )}
              </div>

              {/* 下载区 */}
              <div className="card mt-3 p-4">
                <div className="label mb-2">{t('models.pull.title')}</div>
                <div className="flex flex-wrap gap-2 mb-3">
                  {(local?.recommended || presets?.recommended_models || []).map((r) => (
                    <span
                      key={r.tag}
                      className="chip"
                      title={`${r.note} · ${t('models.pull.aboutSize', { size: r.size_mb })}`}
                      onClick={() => setPullTag(r.tag)}
                    >
                      {r.tag} · ≈{r.size_mb}MB
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    className={`flex-1 px-3 py-2 text-sm ${inputCls}`}
                    placeholder={t('models.pull.tagPh')}
                    value={pullTag}
                    onChange={(e) => setPullTag(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void startPull(pullTag)
                    }}
                  />
                  <button className="btn btn-acc" disabled={pulling || !!activeOp} onClick={() => void startPull(pullTag)}>
                    {pulling || activeOp ? t('models.pull.downloading') : t('common.download')}
                  </button>
                </div>
                <div className="text-2xs mt-2 text-dim">
                  {t('models.pull.note')}
                </div>
                {activeOp && (
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="font-bold">{activeOp.target}</span>
                      <span className="num text-acc">
                        {activeOp.progress}% · {activeOp.message}
                      </span>
                    </div>
                    <div className="h-[4px] bg-bg-3">
                      <div
                        className="h-full transition-all bg-acc"
                        style={{ width: `${activeOp.progress}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            </section>

            {/* ============ 操作记录 ============ */}
            <section id="mc-ops" className="mt-10 mb-10 scroll-mt-4">
              <div className="label mb-3">{t('models.ops.title')}</div>
              {ops.length > 0 ? (
                <div className="card p-4">
                  {ops.map((op) => (
                    <div key={op.id} className="flex items-center gap-3 text-xs py-1">
                      <span className="num text-dim">
                        {formatDateTime(op.created_at)}
                      </span>
                      <span className="font-bold">{t(OP_TYPE_LABEL[op.op_type])}</span>
                      <span>{op.target}</span>
                      <span className={`flex-1 ${
                        op.status === 'succeeded' ? 'text-acc' : op.status === 'failed' ? 'text-bad' : 'text-dim'
                      }`}>
                        {op.status === 'succeeded' ? t('models.ops.succeeded') : op.status === 'failed'
                          ? t('models.ops.failed', { msg: op.error_message || t('models.ops.unknownError') }) : `${op.progress}% ${op.message}`}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="card p-4 text-sm text-dim">
                  {t('models.ops.empty')}
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}
