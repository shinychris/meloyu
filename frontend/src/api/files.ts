import { apiBlob, apiPost, saveBlob } from './client'
import type { ExportRequest, FileRef, StreamTokenResult, Task } from '../types/api'

/** POST /exports —— 发起导出（异步任务，秒级完成，不扣积分） */
export function createExport(req: ExportRequest): Promise<{ task: Task }> {
  return apiPost<{ task: Task }>('/exports', req)
}

/** POST /files/{id}/stream-token —— 短时流地址（15 分钟，供 <audio> 使用） */
export function getStreamToken(fileId: string): Promise<StreamTokenResult> {
  return apiPost<StreamTokenResult>(`/files/${fileId}/stream-token`)
}

/** GET /files/{id}/download —— 鉴权下载（blob 方式携带 Bearer，规避 <a> 标签无法带头） */
export async function downloadFileRef(file: FileRef, fallbackName: string): Promise<void> {
  const blob = await apiBlob(`/files/${file.file_id}/download`)
  saveBlob(blob, file.name || fallbackName)
}
