/** 哼唱成歌（v0.11.0）：录音分析 API。 */
import { apiPost } from './client'
import type { HumAnalysisData } from '../types/api'

/** POST /hum/analyze —— mono wav（octet-stream）→ 音高轮廓（0 积分，不落库）。 */
export function analyzeHum(wav: ArrayBuffer): Promise<HumAnalysisData> {
  return apiPost<HumAnalysisData>('/hum/analyze', wav, {
    headers: { 'Content-Type': 'application/octet-stream' },
    timeout: 60000,
  })
}
