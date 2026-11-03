/**  人声音色档案：注册/双短语采样（octet-stream 协议，与参考音频一致） */
import type { VoiceProfile } from '../types/api'
import { apiDelete, apiGet, apiPost } from './client'

const OCTET = { 'Content-Type': 'application/octet-stream' }
const UPLOAD_TIMEOUT = { timeout: 60000 }

export function enrollVoiceProfile(name: string): Promise<VoiceProfile> {
  return apiPost<VoiceProfile>('/voice-profiles', undefined, {
    params: { name },
    ...UPLOAD_TIMEOUT,
  })
}

export function submitVoiceSample(profileId: string, step: 1 | 2, wav: ArrayBuffer): Promise<VoiceProfile> {
  return apiPost<VoiceProfile>(`/voice-profiles/${profileId}/samples`, wav, {
    params: { step },
    headers: OCTET,
    ...UPLOAD_TIMEOUT,
  })
}

export function listVoiceProfiles(): Promise<{ items: VoiceProfile[]; total: number }> {
  return apiGet('/voice-profiles')
}

export function deleteVoiceProfile(profileId: string): Promise<{ ok: boolean }> {
  return apiDelete(`/voice-profiles/${profileId}`)
}
