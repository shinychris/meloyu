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
import { useMetaStore } from './meta'
import { toast } from './toast'
import { composeStylePrompt } from '../lib/structure'
import { t, getLocale } from '../i18n'
import { studioEn } from '../i18n/en/studio'
import { studioZh } from '../i18n/zh/studio'

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
  /** ：vocal=voice_clone 时必填（已验证音色档案 id） */
  voiceProfileId?: string
  /** 哼唱成歌（v0.11.0）：[[相对半音, 拍长], ...]（hum/analyze 应用后写入） */
  humMelody?: number[][]
}

export interface InspireSelection {
  scene: string
  mood: string
  genre: string
  inst: string
}

/**
 * ：默认风格/歌词为「样例态」——表单字段存空串，展示与提交时按当前
 * locale 现取 t()（LyricsView SAMPLE_TEXTS 同款模式）。模块加载时不再冻结
 * i18n 文案，切换语言后样例自然跟随，不会把旧语言样例提交/回灌进草稿。
 */
export function defaultStylePrompt(): string {
  return t('studio.default.stylePrompt')
}

/** 默认示例歌词（结构标签 [Verse]/[Chorus] 保留英文） */
export function defaultLyrics(): string {
  return t('studio.default.lyrics')
}

/** 全部语言的样例文本（风格描述 + 歌词）：hydrateDraft 时剔除未修改过的旧语言样例 */
const SAMPLE_TEXTS = new Set<string>([
  studioEn['studio.default.stylePrompt'],
  studioZh['studio.default.stylePrompt'],
  studioEn['studio.default.lyrics'],
  studioZh['studio.default.lyrics'],
])

/** 草稿字段是否为「未修改过的样例」（含样例态空串）：是则不回灌，跟随当前语言 */
function isSampleText(v: string | undefined): boolean {
  return v == null || v.trim() === '' || SAMPLE_TEXTS.has(v)
}

const DEFAULT_FORM: StudioForm = {
  mode: 'custom',
  simplePrompt: '',
  stylePrompt: '',
  lyrics: '',
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
  /**
   * 初始「模板已载入」日志是否已被真实操作顶掉（惰性求值）：
   * opLog 本体只存真实操作；模板行由 VersionTree 在 baseLogged=false 时
   * 以当前 locale 现取 t() 渲染，不再在模块加载时冻结文案。
   */
  opLogBaseLogged: boolean
  /**  参考音频：挂到本次生成的参考轨（特征级，提交时带 reference_track_id） */
  referenceTrack: ReferenceTrack | null
  setReferenceTrack: (track: ReferenceTrack) => void
  clearReferenceTrack: () => void
  patchForm: (patch: Partial<StudioForm>) => void
  setInspire: (patch: Partial<InspireSelection>) => void
  /** 把灵感组合写回风格描述（原型 composePrompt） */
  applyInspireToPrompt: (full?: InspireSelection) => void
  /** 随机灵感组合（工作台空态与灵感卡共用， 收敛为单一 action） */
  randomizeInspire: () => void
  /** 采用候选后本地同步 adopted 标记（组件不再绕过 action 直改状态） */
  markAdopted: (candidateId: string) => void
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
  /** 登录/会话就绪后水合该用户的本地草稿 */
  hydrateDraft: (userId: string) => void
}

/* 轮询句柄放模块级：视图卸载也持续轮询，终态/登出停止 */
let pollTimer: number | null = null
let pollErrors = 0

/* ：工作台表单草稿（防误刷新/关标签丢内容）——按用户维度落 localStorage，
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
  opLog: [],
  opLogBaseLogged: false,
  referenceTrack: null,

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

  randomizeInspire() {
    const inspiration = useMetaStore.getState().meta.inspiration
    const pickFrom = (list: string[]) =>
      list.length > 0 ? list[Math.floor(Math.random() * list.length)] : ''
    const next = {
      scene: pickFrom(inspiration.scenes),
      mood: pickFrom(inspiration.moods),
      genre: pickFrom(inspiration.genres),
      inst: pickFrom(inspiration.instruments),
    }
    set({ inspire: next })
    // applyInspireToPrompt 内部已写回风格描述、记日志（原先两处调用各自重复记了一条）
    get().applyInspireToPrompt(next)
    get().markStep(1)
  },

  markAdopted(candidateId) {
    set({ candidates: get().candidates.map((c) => ({ ...c, adopted: c.id === candidateId })) })
  },

  markStep(n) {
    set({ stepDone: { ...get().stepDone, [n]: true } })
  },

  logOp(text) {
    set({ opLog: [text, ...get().opLog].slice(0, 30), opLogBaseLogged: true })
  },

  async submitGeneration(opts) {
    const s = get()
    if (s.submitting) return
    const { form } = s
    if (form.mode === 'simple' && !form.simplePrompt.trim()) {
      toast(t('studio.warn.simpleEmpty'), 'warn')
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
      // 样例态（字段为空）按当前 locale 现取默认示例——与展示所见一致
      req.style_prompt = form.stylePrompt.trim() || t('studio.default.stylePrompt')
      req.lyrics = form.lyrics.trim() ? form.lyrics : t('studio.default.lyrics')
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
    // ：未修改过的样例（任一语言的历史样例/样例态空串）不回灌——
    // 显示值由当前 locale 的样例派生，切语言自然跟随，不锁死旧语言
    const cleaned = Object.fromEntries(
      Object.entries(draft ?? {}).filter(
        ([k, v]) => !((k === 'stylePrompt' || k === 'lyrics') && isSampleText(v as string)),
      ),
    ) as Partial<StudioForm>
    if (Object.keys(cleaned).length > 0) {
      set({ form: { ...DEFAULT_FORM, ...cleaned } })
    }
  },
}))
