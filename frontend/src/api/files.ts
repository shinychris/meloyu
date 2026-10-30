import { apiBlob, apiPost, saveBlob, DOWNLOAD_TIMEOUT_MS } from './client'
import type { ExportRequest, FileRef, StreamTokenResult, Task } from '../types/api'

/** POST /exports —— 发起导出（异步任务，秒级完成，不扣积分） */
export function createExport(req: ExportRequest): Promise<{ task: Task }> {
  return apiPost<{ task: Task }>('/exports', req)
}

/** POST /files/{id}/stream-token —— 短时流地址（15 分钟，供 <audio> 使用） */
export function getStreamToken(fileId: string): Promise<StreamTokenResult> {
  return apiPost<StreamTokenResult>(`/files/${fileId}/stream-token`)
}

/** GET /files/{id}/download —— 鉴权下载（blob 方式携带 Bearer，规避 <a> 标签无法带头）。
 *  大文件下载：超时放宽到 300s（F-FE-07），不受全局 20s 网关超时约束。 */
export async function downloadFileRef(file: FileRef, fallbackName: string): Promise<void> {
  const blob = await apiBlob(`/files/${file.file_id}/download`, { timeout: DOWNLOAD_TIMEOUT_MS })
  saveBlob(blob, file.name || fallbackName)
}

/**
 * 下载音频字节并解码用（stream-token 短时 URL，带签名 query，非 /api/v1 通道）。
 * F-FE-06：组件不再裸 fetch——此处统一校验 r.ok，非 2xx（403/404/错误页 HTML）
 * 抛错，由调用方显式 toast，不再把错误页字节喂给 decodeAudioData 静默失败。
 */
export async function fetchAudioBytes(url: string): Promise<ArrayBuffer> {
  const r = await fetch(url)
  if (!r.ok) {
    throw new Error(`audio download failed: HTTP ${r.status}`)
  }
  // 流式读为 blob 再取字节，避免大文件一次性 read 附带的多余拷贝
  const blob = await r.blob()
  return blob.arrayBuffer()
}
