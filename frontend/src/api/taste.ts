/** V2-b 我的口味：画像读取与重建（建议值预填语义） */
import { apiGet, apiPost } from './client'

export interface TasteProfileData {
  profile: {
    bpm: number | null
    key: string | null
    density: number | null
    vocal: string | null
    language: string | null
    top_tags: string[]
  }
  sample_count: number
  updated_at: string
  semantics: [string, string]
}

export function getTaste(): Promise<TasteProfileData> {
  return apiGet('/taste')
}

export function rebuildTaste(): Promise<TasteProfileData> {
  return apiPost('/taste/rebuild')
}
