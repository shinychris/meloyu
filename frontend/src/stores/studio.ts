import { create } from 'zustand'
import type {
  Candidate,
  GenerationSubmitRequest,
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
}

export interface InspireSelection {
  scene: string
  mood: string
  genre: string
  inst: string
}

const DEFAULT_FORM: StudioForm = {
  mode: 'custom',
  simplePrompt: '',
  stylePrompt: '华语流行抒情，钢琴主导，弦乐铺底，雨夜氛围，女声气声，副歌情绪推起',
  lyrics: '[Verse]\n雨停在凌晨三点的窗台\n霓虹把影子拉得好白\n[Chorus]\n我们把未来说得太轻\n像风穿过无人的街心',
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
}

/* 轮询句柄放模块级：视图卸载也持续轮询（契约 §13.2），终态/登出停止 */
let pollTimer: number | null = null
let pollErrors = 0

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
          ? task.error?.message ?? '生成失败'
          : '已取消生成，积分已退还'
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
      useStudioStore.setState({ submitting: false, failureMessage: '任务状态查询中断，请稍后重试' })
      toast('任务状态查询中断，请稍后重试', 'bad')
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
      if (result.inferred_structure) toast('歌词无结构标签，已自动补全结构')
      // 候选数以接口为准（生成固定 2 个；延长/变体/段落重生成等派生操作可能不同）
      const n = result.items.length
      s.logOp(n > 0 ? `生成 ${n} 个候选（任务已完成）` : '生成完成（任务已完成）')
      toast(n > 0 ? `已生成 ${n} 个候选` : '生成完成')
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
  opLog: ['载入模板「华语流行抒情」'],

  patchForm(patch) {
    set({ form: { ...get().form, ...patch } })
  },

  setInspire(patch) {
    set({ inspire: { ...get().inspire, ...patch } })
  },

  applyInspireToPrompt(full) {
    const inspire = full ?? get().inspire
    const prompt = composeStylePrompt(inspire)
    if (prompt) {
      get().patchForm({ stylePrompt: prompt })
      get().logOp(`灵感指引：${prompt.split('，').join(' / ')}`)
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
      toast('先用一句话描述你想写的歌', 'warn')
      return
    }
    if (form.mode === 'custom' && !form.stylePrompt.trim()) {
      toast('风格描述不能为空', 'warn')
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
      },
    }
    if (form.mode === 'simple') {
      req.simple_prompt = form.simplePrompt.trim()
    } else {
      req.style_prompt = form.stylePrompt.trim()
      req.lyrics = form.lyrics
    }
    set({ submitting: true, failureMessage: null, candidates: [], task: null })
    try {
      const result = await submitGeneration(req)
      set({ task: result.task, workId: result.work.id, workTitle: result.work.title })
      get().logOp(
        `提交生成（${result.cost_credits} 积分）${opts?.simplified ? ' · 精简重试' : ''}`,
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
      toast('已请求取消，正在停止…')
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
    get().logOp(`${opLabel}（${result.cost_credits} 积分）→ ${result.work.display_code} 新子版本生成中`)
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
}))
