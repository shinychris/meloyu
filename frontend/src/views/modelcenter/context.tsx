import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type {
  LLMSettings,
  LyricsBackend,
  ModelOpInfo,
  ModelsRuntime,
  MusicBackend,
  MusicCatalog,
  MusicCatalogModel,
} from '../../types/api'
import type { LocalModelsResult, ModelsPresets } from '../../types/api'
import {
  deleteMusicModel,
  deployAceStep,
  getLLMSettings,
  getLocalModels,
  getModelOp,
  getModelsPresets,
  getModelsRuntime,
  getMusicCatalog,
  listModelOps,
  pullMusicModel,
  updateLLMSettings,
} from '../../api/models'
import { useConfirmStore } from '../../stores/confirm'
import { toast } from '../../stores/toast'
import { t } from '../../i18n'

/**
 * 模型中心共享状态（F-FE-09 拆分）：
 * 服务端数据（runtime/local/settings/presets/ops/catalog）与跨区块共享的可变
 * 草稿（通道选择、外部端点、slug/host 编辑、Replicate Token）收敛到 Provider；
 * 各 section 组件只保留本区块的瞬态（测试中/测试结果等）。
 * 行为与拆分前完全一致——refreshAll 仍按原字段逐一重置草稿。
 */

interface ModelCenterContextValue {
  // 服务端数据
  runtime: ModelsRuntime | null
  local: LocalModelsResult | null
  settings: LLMSettings | null
  presets: ModelsPresets | null
  ops: ModelOpInfo[]
  catalog: MusicCatalog | null
  setRuntime: (v: ModelsRuntime | null) => void
  setLocal: (v: LocalModelsResult | null) => void
  setSettings: (v: LLMSettings | null) => void
  setCatalog: (v: MusicCatalog | null) => void
  // 跨区块共享草稿
  backend: LyricsBackend
  setBackend: (v: LyricsBackend) => void
  pickedModel: string
  setPickedModel: (v: string) => void
  musicBackend: MusicBackend
  setMusicBackend: (v: MusicBackend) => void
  musicBase: string
  setMusicBase: (v: string) => void
  musicModel: string
  setMusicModel: (v: string) => void
  extBase: string
  setExtBase: (v: string) => void
  extModel: string
  setExtModel: (v: string) => void
  extKey: string
  setExtKey: (v: string) => void
  ollamaHostEdit: string
  setOllamaHostEdit: (v: string) => void
  slugEdits: Record<string, string>
  setSlugEdits: (v: Record<string, string>) => void
  hostEdits: Record<string, string>
  setHostEdits: (v: Record<string, string>) => void
  replicateKey: string
  setReplicateKey: (v: string) => void
  // 共享执行态
  saving: boolean
  setSaving: (v: boolean) => void
  catalogBusy: boolean
  setCatalogBusy: (v: boolean) => void
  activeOp: ModelOpInfo | null
  setActiveOp: (v: ModelOpInfo | null) => void
  // 共享动作
  refreshAll: () => Promise<void>
  saveBackend: (target: LyricsBackend, extra?: Record<string, string>) => Promise<void>
  startAceDeploy: () => Promise<void>
  downloadMusicModel: (m: MusicCatalogModel) => Promise<void>
  removeMusicModel: (m: MusicCatalogModel) => Promise<void>
}

const ModelCenterContext = createContext<ModelCenterContextValue | null>(null)

export function useModelCenter(): ModelCenterContextValue {
  const ctx = useContext(ModelCenterContext)
  if (!ctx) throw new Error('useModelCenter must be used within ModelCenterProvider')
  return ctx
}

export function ModelCenterProvider({ children }: { children: ReactNode }) {
  const confirm = useConfirmStore((s) => s.confirm)

  const [runtime, setRuntime] = useState<ModelsRuntime | null>(null)
  const [local, setLocal] = useState<LocalModelsResult | null>(null)
  const [settings, setSettings] = useState<LLMSettings | null>(null)
  const [presets, setPresets] = useState<ModelsPresets | null>(null)
  const [ops, setOps] = useState<ModelOpInfo[]>([])
  const [catalog, setCatalog] = useState<MusicCatalog | null>(null)

  const [backend, setBackend] = useState<LyricsBackend>('localsynth')
  const [pickedModel, setPickedModel] = useState('')

  const [musicBackend, setMusicBackend] = useState<MusicBackend>('localsynth')
  const [musicBase, setMusicBase] = useState('')
  const [musicModel, setMusicModel] = useState('')

  const [extBase, setExtBase] = useState('')
  const [extKey, setExtKey] = useState('')
  const [extModel, setExtModel] = useState('')
  const [saving, setSaving] = useState(false)

  const [ollamaHostEdit, setOllamaHostEdit] = useState('')

  const [slugEdits, setSlugEdits] = useState<Record<string, string>>({})
  const [hostEdits, setHostEdits] = useState<Record<string, string>>({})
  const [catalogBusy, setCatalogBusy] = useState(false)
  const [replicateKey, setReplicateKey] = useState('')

  const [activeOp, setActiveOp] = useState<ModelOpInfo | null>(null)
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

  // 下载进度轮询（2s，终态刷新列表与操作记录）。
  // ACE-Step 组件部署在桌面首启后台自动发起时（v0.16.3 默认安装即部署）：
  // 目录快照命中进行中的部署操作即接管为显式轮询态（首次 tick 落 activeOp），
  // 进度卡片实时化——以派生值替代同步 setState 副作用（react-hooks/set-state-in-effect）
  const deploySnap = catalog?.machine.acestep_deploy_op ?? null
  const adoptDeploy =
    !activeOp && deploySnap && (deploySnap.status === 'queued' || deploySnap.status === 'running')
      ? deploySnap
      : null
  const effectiveOp = activeOp ?? adoptDeploy

  useEffect(() => {
    if (!effectiveOp || (effectiveOp.status !== 'queued' && effectiveOp.status !== 'running')) {
      if (activeOp) {
        void refreshAll().catch(() => {})
        setActiveOp(null)
      }
      return
    }
    pollRef.current = window.setInterval(async () => {
      try {
        const op = await getModelOp(effectiveOp.id)
        setActiveOp(op)
      } catch {
        /* 下一轮重试 */
      }
    }, 2000)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [effectiveOp, activeOp, refreshAll])

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

  const value: ModelCenterContextValue = {
    runtime, local, settings, presets, ops, catalog,
    setRuntime, setLocal, setSettings, setCatalog,
    backend, setBackend,
    pickedModel, setPickedModel,
    musicBackend, setMusicBackend,
    musicBase, setMusicBase,
    musicModel, setMusicModel,
    extBase, setExtBase,
    extModel, setExtModel,
    extKey, setExtKey,
    ollamaHostEdit, setOllamaHostEdit,
    slugEdits, setSlugEdits,
    hostEdits, setHostEdits,
    replicateKey, setReplicateKey,
    saving, setSaving,
    catalogBusy, setCatalogBusy,
    activeOp, setActiveOp,
    refreshAll, saveBackend, startAceDeploy, downloadMusicModel, removeMusicModel,
  }

  return <ModelCenterContext.Provider value={value}>{children}</ModelCenterContext.Provider>
}
