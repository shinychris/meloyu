import { create } from 'zustand'
import type {
  Candidate,
  GenerationSubmitRequest,
  ReferenceTrack,
  GenerationSubmitResult,
  KeyMode,
  Language,
  Mode,
  ModelId,
  Task,
  TimeSignature,
  Tonic,
  VersionTreeData,
  VocalType,
} from '../types/api'
import { cancelTask, getTask, listCandidates, submitGeneration } from '../api/generation'
import { getVersionTree } from '../api/works'
import { useSessionStore } from './session'
import { toast } from './toast'
import { composeStylePrompt } from '../lib/structure'
import { t, getLocale } from '../i18n'

export interface StudioForm {
  mode: Mode
  simplePrompt: string
  stylePrompt: string
  lyrics: string
  negativePrompt: string
  model: ModelId
  bpm: number
  keyTonic: Tonic
  keyMode: KeyMode
  timeSignature: TimeSignature
  durationSec: number
  vocal: VocalType
  language: Language
  density: number
  /** FR-5：vocal=voice_clone 时必填（已验证音色档案 id） */
  voiceProfileId?: string
  /** 哼唱成歌（v0.11.0）：[[相对半音, 拍长], ...]（/hum/analyze 应用后写入） */
  humMelody?: number[][]
}

export interface InspireSelection {
  scene: string
  mood: string
  genre: string
  inst: string
}

/** 新会话默认风格描述（示例输入内容，按当前 locale 取文案；文件顶部已 import t，无初始化时序问题） */
function initialStylePrompt(): string {
  return t('studio.default.stylePrompt')
}

/** 新会话默认示例歌词（结构标签 [Verse]/[Chorus] 保留英文） */
function initialLyrics(): string {
  return t('studio.default.lyrics')
}

const DEFAULT_FORM: StudioForm = {
  mode: 'custom',
  simplePrompt: '',
  stylePrompt: initialStylePrompt(),
  lyrics: initialLyrics(),
  negativePrompt: '',
  model: 'v1_pro',
  bpm: 90,
  keyTonic: 'A',
  keyMode: 'minor',
  timeSignature: '4/4',
  durationSec: 210,
  vocal: 'female_air',
  language: 'zh',
  density: 65,
}

interface StudioState {
  form: StudioForm
  inspire: InspireSelection
  /** 1~3 步是否已点亮（原型 markStep），第 4 步在生成时点亮 */
  stepDone: Record<1 | 2 | 3, boolean>
  workId: string | null
  workTitle: string | null
  versionTree: VersionTreeData | null
  task: Task | null
  candidates: Candidate[]
  inferredStructure: boolean
  submitting: boolean
  failureMessage: string | null
  opLog: string[]
  /** FR-4 参考音频：挂到本次生成的参考轨（特征级，提交时带 reference_track_id） */
  referenceTrack: ReferenceTrack | null
  setReferenceTrack: (track: ReferenceTrack) => void
  clearReferenceTrack: () => void
  patchForm: (patch: Partial<StudioForm>) => void
  setInspire: (patch: Partial<InspireSelection>) => void
  /** 把灵感组合写回风格描述（原型 composePrompt） */
  applyInspireToPrompt: (full?: InspireSelection) => void
  markStep: (n: 1 | 2 | 3) => void
  logOp: (text: string) => void
  submitGeneration: (opts?: { simplified?: boolean }) => Promise<void>
  /** 延长/变体/段落重生成（V1.1）提交成功后接管任务轮询（响应复用 generations 形态） */
  startDerivedGeneration: (result: GenerationSubmitResult, opLabel: string) => void
  cancelGeneration: () => Promise<void>
  startPolling: (taskId: string) => void
  stopPolling: () => void
  refreshVersionTree: () => Promise<void>
  resetForNewWork: () => void
  setLyricsFromAssistant: (lyrics: string) => void
  /** 登录/会话就绪后水合该用户的本地草稿（P1-23） */
  hydrateDraft: (userId: string) => void
}

/* 轮询句柄放模块级：视图卸载也持续轮询（契约 §13.2），终态/登出停止 */
let pollTimer: number | null = null
let pollErrors = 0

/* P1-23：工作台表单草稿（防误刷新/关标签丢内容）——按用户维度落 localStorage，
 * 500ms 防抖写入；提交成功不清（用户常基于上次参数迭代）。 */
const draftKey = (userId: string) => `meloyu:studio-draft:v1:${userId}`
let draftTimer: number | null = null

function persistDraft(userId: string | null, form: StudioForm): void {
  if (!userId || typeof localStorage === 'undefined') return
  if (draftTimer != null) window.clearTimeout(draftTimer)
  draftTimer = window.setTimeout(() => {
    try {
      localStorage.setItem(draftKey(userId), JSON.stringify(form))
    } catch {
      /* 配额满等异常静默：草稿是尽力而为的保护 */
    }
  }, 500)
}

function readDraft(userId: string): Partial<StudioForm> | null {
  try {
    const raw = localStorage.getItem(draftKey(userId))
    return raw ? (JSON.parse(raw) as Partial<StudioForm>) : null
  } catch {
    return null
  }
}

function schedulePoll(getState: () => StudioState, taskId: string, delay = 1500) {
  if (pollTimer != null) window.clearTimeout(pollTimer)
  pollTimer = window.setTimeout(() => void pollTick(getState, taskId), delay)
}

async function pollTick(getState: () => StudioState, taskId: string) {
  try {
    const task = await getTask(taskId)
    pollErrors = 0
    useStudioStore.setState({ task })
    if (task.status === 'succeeded') {
      useStudioStore.getState().stopPolling()
      await onGenerationSucceeded(task)
    } else if (task.status === 'failed' || task.status === 'canceled') {
      useStudioStore.getState().stopPolling()
      const msg =
        task.status === 'failed'
          ? task.error?.message ?? t('studio.fail.default')
          : t('studio.fail.canceled')
      useStudioStore.setState({
        submitting: false,
        failureMessage: task.status === 'failed' ? msg : null,
      })
      if (task.status === 'failed') toast(msg, 'bad')
    } else {
      schedulePoll(getState, taskId)
    }
  } catch {
    pollErrors++
    if (pollErrors >= 5) {
      useStudioStore.getState().stopPolling()
      useStudioStore.setState({ submitting: false, failureMessage: t('studio.fail.pollLost') })
      toast(t('studio.fail.pollLost'), 'bad')
    } else {
      schedulePoll(getState, taskId, 1500)
    }
  }
}

async function onGenerationSucceeded(task: Task) {
  const s = useStudioStore.getState()
  if (task.version_id) {
    try {
      const result = await listCandidates(task.version_id)
      useStudioStore.setState({
        candidates: result.items,
        inferredStructure: result.inferred_structure,
      })
      if (result.inferred_structure) toast(t('studio.toast.structureInferred'))
      // 候选数以接口为准（生成固定 2 个；延长/变体/段落重生成等派生操作可能不同）
      const n = result.items.length
      s.logOp(n > 0 ? t('studio.log.generated', { n }) : t('studio.log.generatedEmpty'))
      toast(n > 0 ? t('studio.toast.generated', { n }) : t('studio.toast.generatedEmpty'))
    } catch {
      /* 拦截器已 toast */
    }
  }
  useStudioStore.setState({ submitting: false, failureMessage: null })
  void s.refreshVersionTree()
  void useSessionStore.getState().refreshUser()
}

export const useStudioStore = create<StudioState>((set, get) => ({
  form: { ...DEFAULT_FORM },
  inspire: { scene: '', mood: '', genre: '', inst: '' },
  stepDone: { 1: false, 2: false, 3: false },
  workId: null,
  workTitle: null,
  versionTree: null,
  task: null,
  candidates: [],
  inferredStructure: false,
  submitting: false,
  failureMessage: null,
  referenceTrack: null,
  opLog: [t('studio.log.templateLoaded')],

  setReferenceTrack(track) {
    set({ referenceTrack: track })
  },

  clearReferenceTrack() {
    set({ referenceTrack: null })
  },

  patchForm(patch) {
    const next = { ...get().form, ...patch }
    set({ form: next })
    persistDraft(useSessionStore.getState().user?.id ?? null, next)
  },

  setInspire(patch) {
    set({ inspire: { ...get().inspire, ...patch } })
  },

  applyInspireToPrompt(full) {
    const inspire = full ?? get().inspire
    const prompt = composeStylePrompt(inspire)
    if (prompt) {
      get().patchForm({ stylePrompt: prompt })
      // composeStylePrompt 按 locale 用「，」/「, 」连接，日志统一转为「 / 」分隔
      const detail = prompt.split(getLocale() === 'en' ? ', ' : '，').join(' / ')
      get().logOp(t('studio.log.inspire', { detail }))
    }
  },

  markStep(n) {
    set({ stepDone: { ...get().stepDone, [n]: true } })
  },

  logOp(text) {
    set({ opLog: [text, ...get().opLog].slice(0, 30) })
  },

  async submitGeneration(opts) {
    const s = get()
    if (s.submitting) return
    const { form } = s
    if (form.mode === 'simple' && !form.simplePrompt.trim()) {
      toast(t('studio.warn.simpleEmpty'), 'warn')
      return
    }
    if (form.mode === 'custom' && !form.stylePrompt.trim()) {
      toast(t('studio.warn.styleEmpty'), 'warn')
      return
    }
    const req: GenerationSubmitRequest = {
      mode: form.mode,
      model: form.model,
      negative_prompt: form.negativePrompt,
      work_id: s.workId ?? undefined,
      simplified: opts?.simplified,
      params: {
        bpm: form.bpm,
        key: { tonic: form.keyTonic, mode: form.keyMode },
        time_signature: form.timeSignature,
        duration_sec: form.durationSec,
        vocal: form.vocal,
        language: form.language,
        instrument_density: form.density,
        ...(form.vocal === 'voice_clone' && form.voiceProfileId
          ? { voice_profile_id: form.voiceProfileId }
          : {}),
        ...(form.humMelody && form.humMelody.length >= 2
          ? { hum_melody: form.humMelody }
          : {}),
      },
    }
    if (form.mode === 'simple') {
      req.simple_prompt = form.simplePrompt.trim()
    } else {
      req.style_prompt = form.stylePrompt.trim()
      req.lyrics = form.lyrics
    }
    if (s.referenceTrack) {
      req.reference_track_id = s.referenceTrack.id
    }
    set({ submitting: true, failureMessage: null, candidates: [], task: null })
    try {
      const result = await submitGeneration(req)
      set({ task: result.task, workId: result.work.id, workTitle: result.work.title })
      // license（桌面买断）模式：用量纯计量无余额语义，跳过余额刷新、
      // 日志按用量口径；cloud 形态积分在提交时即扣，立刻同步侧栏（测试发现 #5）
      const metered = useSessionStore.getState().license?.billing_mode === 'license'
      if (!metered) void useSessionStore.getState().refreshCredits()
      get().logOp(
        opts?.simplified
          ? t(metered ? 'studio.log.submitSimplifiedLocal' : 'studio.log.submitSimplified', { n: result.cost_credits })
          : t(metered ? 'studio.log.submitLocal' : 'studio.log.submit', { n: result.cost_credits }),
      )
      get().startPolling(result.task.id)
    } catch {
      set({ submitting: false })
    }
  },

  async cancelGeneration() {
    const task = get().task
    if (!task || !['queued', 'running'].includes(task.status)) return
    try {
      const updated = await cancelTask(task.id)
      set({ task: updated })
      toast(t('studio.toast.cancelRequested'))
    } catch {
      /* 拦截器已 toast */
    }
  },

  /**
   * V1.1 派生操作（延长/变体/段落重生成）提交成功后的接管入口：
   * 置为「生成中」态、清空旧候选、指向新作品上下文并启动既有 1.5s 轮询；
   * 成功后 onGenerationSucceeded 会拉取新子版本候选并刷新版本树。
   */
  startDerivedGeneration(result, opLabel) {
    set({
      task: result.task,
      workId: result.work.id,
      workTitle: result.work.title,
      submitting: true,
      failureMessage: null,
      candidates: [],
    })
    get().logOp(
      t(
        useSessionStore.getState().license?.billing_mode === 'license'
          ? 'studio.log.deriveStartLocal'
          : 'studio.log.deriveStart',
        {
          op: opLabel,
          n: result.cost_credits,
          code: result.work.display_code,
        },
      ),
    )
    get().startPolling(result.task.id)
  },

  startPolling(taskId) {
    pollErrors = 0
    if (pollTimer != null) window.clearTimeout(pollTimer)
    void pollTick(() => useStudioStore.getState(), taskId)
  },

  stopPolling() {
    if (pollTimer != null) {
      window.clearTimeout(pollTimer)
      pollTimer = null
    }
  },

  async refreshVersionTree() {
    const workId = get().workId
    if (!workId) return
    try {
      const tree = await getVersionTree(workId)
      set({ versionTree: tree })
    } catch {
      /* 拦截器已 toast */
    }
  },

  resetForNewWork() {
    get().stopPolling()
    set({
      workId: null,
      workTitle: null,
      versionTree: null,
      task: null,
      candidates: [],
      inferredStructure: false,
      submitting: false,
      failureMessage: null,
    })
  },

  setLyricsFromAssistant(lyrics) {
    get().patchForm({ lyrics })
    get().markStep(2)
  },

  hydrateDraft(userId) {
    const draft = readDraft(userId)
    if (draft && Object.keys(draft).length > 0) {
      set({ form: { ...DEFAULT_FORM, ...draft } })
    }
  },
}))
