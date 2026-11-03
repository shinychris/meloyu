/**
 * 协作评论 API（团队协作段）。
 * ：从 CommentsPanel 组件内联请求收敛到 api/ 分层。
 */
import { apiDelete, apiGet, apiPatch, apiPost } from './client'
import type { WorkCommentItem } from '../types/api'

/** GET /works/{id}/comments —— 作品评论列表（时间轴锚点升序） */
export function listComments(workId: string): Promise<{ items: WorkCommentItem[]; total: number }> {
  return apiGet(`/works/${workId}/comments`)
}

/** POST /works/{id}/comments —— 发表评论（锚定当前播放位置） */
export function createComment(
  workId: string,
  req: { time_sec: number; body: string },
): Promise<WorkCommentItem> {
  return apiPost(`/works/${workId}/comments`, req)
}

/** PATCH /comments/{id} —— 标记 resolved / 重开 */
export function resolveComment(commentId: string, resolved: boolean): Promise<WorkCommentItem> {
  return apiPatch(`/comments/${commentId}`, { resolved })
}

/** DELETE /comments/{id} —— 删除评论（作者或更高角色，服务端校验） */
export function deleteComment(commentId: string): Promise<{ ok: boolean }> {
  return apiDelete(`/comments/${commentId}`)
}
