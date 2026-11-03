import { apiGet, apiPost } from './client'
import type {
  Candidate,
  CandidatesResult,
  ExtendCandidateRequest,
  GenerationSubmitRequest,
  GenerationSubmitResult,
  Paginated,
  RegenSectionRequest,
  Task,
  VariantCandidateRequest,
  Version,
  PitchEditRequest,
} from '../types/api'

/** POST /generations —— 提交生成（原子扣积分，产出 2 候选） */
export function submitGeneration(req: GenerationSubmitRequest): Promise<GenerationSubmitResult> {
  return apiPost<GenerationSubmitResult>('/generations', req)
}

/** GET /tasks —— 任务列表 */
export function listTasks(params?: {
  type?: 'generation' | 'export'
  status?: string
  work_id?: string
  page?: number
  page_size?: number
}): Promise<Paginated<Task>> {
  return apiGet<Paginated<Task>>('/tasks', params)
}

/** GET /tasks/{id} —— 轮询任务状态（前端 1.5s，终态停止） */
export function getTask(taskId: string): Promise<Task> {
  return apiGet<Task>(`/tasks/${taskId}`)
}

/** POST /tasks/{id}/cancel —— 取消任务（积分全退） */
export function cancelTask(taskId: string): Promise<Task> {
  return apiPost<Task>(`/tasks/${taskId}/cancel`)
}

/** GET /versions/{version_id}/candidates —— 候选列表 */
export function listCandidates(versionId: string): Promise<CandidatesResult> {
  return apiGet<CandidatesResult>(`/versions/${versionId}/candidates`)
}

/** GET /candidates/{id} —— 候选详情 */
export function getCandidate(candidateId: string): Promise<Candidate> {
  return apiGet<Candidate>(`/candidates/${candidateId}`)
}

/** POST /candidates/{id}/adopt —— 采用候选（定稿当前版本） */
export function adoptCandidate(candidateId: string): Promise<Version> {
  return apiPost<Version>(`/candidates/${candidateId}/adopt`)
}

/* ============ V1.1 候选派生操作 ============ */
// 三接口响应复用 POST /generations 的 { task, work, cost_credits } 形态，
// 提交后由 stores/studio.ts 复用生成轮询；后端未升级时返回 501/50101（拦截器 toast）。

/** POST /candidates/{id}/extend —— 延长：从结尾续写 {seconds:15~60}，生成子版本 */
export function extendCandidate(
  candidateId: string,
  req: ExtendCandidateRequest,
): Promise<GenerationSubmitResult> {
  return apiPost<GenerationSubmitResult>(`/candidates/${candidateId}/extend`, req)
}

/** POST /candidates/{id}/variant —— 变体：同结构换风格生成子版本；style_prompt 缺省=自动换风格 */
export function variantCandidate(
  candidateId: string,
  req: VariantCandidateRequest,
): Promise<GenerationSubmitResult> {
  return apiPost<GenerationSubmitResult>(`/candidates/${candidateId}/variant`, req)
}

/** POST /candidates/{id}/regen-section —— 段落重生成：仅重生成该段，其余段不变 */
export function regenSectionCandidate(
  candidateId: string,
  req: RegenSectionRequest,
): Promise<GenerationSubmitResult> {
  return apiPost<GenerationSubmitResult>(`/candidates/${candidateId}/regen-section`, req)
}

/** POST /candidates/{id}/pitch-edit（v0.11.0）—— 音符级移调/量化，同 seed 确定性重渲染 */
export function pitchEditCandidate(
  candidateId: string,
  req: PitchEditRequest,
): Promise<GenerationSubmitResult> {
  return apiPost<GenerationSubmitResult>(`/candidates/${candidateId}/pitch-edit`, req)
}
