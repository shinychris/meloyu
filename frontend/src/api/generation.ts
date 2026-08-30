import { apiGet, apiPost } from './client'
import type {
  Candidate,
  CandidatesResult,
  GenerationSubmitRequest,
  GenerationSubmitResult,
  Paginated,
  Task,
  Version,
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

/** V1.1 占位接口（MVP 返回 501/50101，前端按钮给「即将上线」提示） */
export function extendCandidate(candidateId: string): Promise<never> {
  return apiPost<never>(`/candidates/${candidateId}/extend`)
}
