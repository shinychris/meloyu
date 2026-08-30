import { apiBlob, apiDelete, apiGet, apiPatch, apiPost, saveBlob } from './client'
import type {
  Certificate,
  EditEvent,
  Paginated,
  Version,
  VersionTreeData,
  Work,
  WorkDeleteResult,
  WorkListQuery,
  WorkPatchRequest,
} from '../types/api'

/** GET /works —— 作品列表（筛选/搜索/排序/分页） */
export function listWorks(query?: WorkListQuery): Promise<Paginated<Work>> {
  return apiGet<Paginated<Work>>('/works', query as Record<string, unknown> | undefined)
}

/** GET /works/{id} —— 作品详情 */
export function getWork(workId: string): Promise<Work> {
  return apiGet<Work>(`/works/${workId}`)
}

/** PATCH /works/{id} —— 更新标题/标签/收藏（乐观更新边界内） */
export function patchWork(workId: string, req: WorkPatchRequest): Promise<Work> {
  return apiPatch<Work>(`/works/${workId}`, req)
}

/** DELETE /works/{id}?permanent= —— 软删进回收站 / 物理删除 */
export function deleteWork(workId: string, permanent: boolean): Promise<WorkDeleteResult> {
  return apiDelete<WorkDeleteResult>(`/works/${workId}`, { permanent })
}

/** POST /works/{id}/restore —— 从回收站恢复 */
export function restoreWork(workId: string): Promise<Work> {
  return apiPost<Work>(`/works/${workId}/restore`)
}

/** GET /works/{id}/events —— 操作留痕（合规中心数据源） */
export function listWorkEvents(
  workId: string,
  params?: { page?: number; page_size?: number },
): Promise<Paginated<EditEvent>> {
  return apiGet<Paginated<EditEvent>>(`/works/${workId}/events`, params)
}

/** GET /works/{id}/versions —— 版本树 */
export function getVersionTree(workId: string): Promise<VersionTreeData> {
  return apiGet<VersionTreeData>(`/works/${workId}/versions`)
}

/** GET /versions/{id} —— 版本详情（参数与歌词快照） */
export function getVersion(versionId: string): Promise<Version> {
  return apiGet<Version>(`/versions/${versionId}`)
}

/**
 * GET /versions/{id}/certificate —— 授权证书（同步下载，响应为非包裹 JSON）。
 * 展示用：blob → text → JSON.parse。
 */
export async function fetchCertificate(versionId: string): Promise<Certificate> {
  const blob = await apiBlob(`/versions/${versionId}/certificate`)
  const text = await blob.text()
  return JSON.parse(text) as Certificate
}

/** 下载证书 JSON 文件（契约 §8.4：attachment 文件名由后端定，此处前端命名兜底） */
export async function downloadCertificate(versionId: string, filename: string): Promise<void> {
  const blob = await apiBlob(`/versions/${versionId}/certificate`)
  saveBlob(blob, filename)
}
