import { apiPost } from './client'
import type {
  CompleteTagsResult,
  LyricsGenerateRequest,
  LyricsGenerateResult,
  LyricsPolishRequest,
  LyricsPolishResult,
  RhymeCheckResult,
} from '../types/api'

/** POST /lyrics/generate —— AI 生成歌词（同步 <3s） */
export function generateLyrics(req: LyricsGenerateRequest): Promise<LyricsGenerateResult> {
  return apiPost<LyricsGenerateResult>('/lyrics/generate', req)
}

/** POST /lyrics/polish —— 润色（可锁定行 / 只润色某段） */
export function polishLyrics(req: LyricsPolishRequest): Promise<LyricsPolishResult> {
  return apiPost<LyricsPolishResult>('/lyrics/polish', req)
}

/** POST /lyrics/rhyme-check —— 押韵 / 重音检查 */
export function rhymeCheck(lyrics: string): Promise<RhymeCheckResult> {
  return apiPost<RhymeCheckResult>('/lyrics/rhyme-check', { lyrics })
}

/** POST /lyrics/complete-tags —— 结构标签补全 */
export function completeTags(lyrics: string): Promise<CompleteTagsResult> {
  return apiPost<CompleteTagsResult>('/lyrics/complete-tags', { lyrics })
}
