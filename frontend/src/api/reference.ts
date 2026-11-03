/**  参考音频：octet-stream 上传（无 python-multipart 依赖的轻协议） */
import type { ReferenceTrack, ReferenceTrackList } from '../types/api'
import { apiDelete, apiGet, apiPost } from './client'

const OCTET = { 'Content-Type': 'application/octet-stream' }
// 上传含 8 分钟音频 + 服务端秒级分析：放宽到 120s
const UPLOAD_TIMEOUT = { timeout: 120000 }

export function uploadReferenceTrack(filename: string, bytes: ArrayBuffer | Uint8Array): Promise<ReferenceTrack> {
  return apiPost<ReferenceTrack>('/reference-tracks', bytes, {
    params: { filename },
    headers: OCTET,
    ...UPLOAD_TIMEOUT,
  })
}

export function attachAnalysisWav(trackId: string, bytes: ArrayBuffer | Uint8Array): Promise<ReferenceTrack> {
  return apiPost<ReferenceTrack>(`/reference-tracks/${trackId}/analysis-wav`, bytes, {
    headers: OCTET,
    ...UPLOAD_TIMEOUT,
  })
}

export function listReferenceTracks(page = 1, pageSize = 20): Promise<ReferenceTrackList> {
  return apiGet<ReferenceTrackList>('/reference-tracks', { page, page_size: pageSize })
}

export function getReferenceTrack(trackId: string): Promise<ReferenceTrack> {
  return apiGet<ReferenceTrack>(`/reference-tracks/${trackId}`)
}

export function deleteReferenceTrack(trackId: string): Promise<{ ok: boolean }> {
  return apiDelete<{ ok: boolean }>(`/reference-tracks/${trackId}`)
}
