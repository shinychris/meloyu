import { apiPost } from './client'
import type {
  CompleteTagsResult,
  LyricsGenerateRequest,
  LyricsGenerateResult,
  LyricsPolishRequest,
  LyricsPolishResult,
  RhymeCheckResult,
} from '../types/api'

/** V1.2：LLM 通道（本地模型/外部 API）生成一首歌词最长数分钟（视模型而定） */
const LLM_TIMEOUT = { timeout: 330000 }

/** POST /lyrics/generate —— AI 生成歌词（本地规则秒级；LLM 通道视模型 10s~3min） */
export function generateLyrics(req: LyricsGenerateRequest): Promise<LyricsGenerateResult> {
  return apiPost<LyricsGenerateResult>('/lyrics/generate', req, LLM_TIMEOUT)
}

/** POST /lyrics/polish —— 润色（可锁定行 / 只润色某段） */
export function polishLyrics(req: LyricsPolishRequest): Promise<LyricsPolishResult> {
  return apiPost<LyricsPolishResult>('/lyrics/polish', req, LLM_TIMEOUT)
}

/** POST /lyrics/rhyme-check —— 押韵 / 重音检查（本地规则计算，恒快） */
export function rhymeCheck(lyrics: string): Promise<RhymeCheckResult> {
  return apiPost<RhymeCheckResult>('/lyrics/rhyme-check', { lyrics })
}

/** POST /lyrics/complete-tags —— 结构标签补全（本地规则计算，恒快） */
export function completeTags(lyrics: string): Promise<CompleteTagsResult> {
  return apiPost<CompleteTagsResult>('/lyrics/complete-tags', { lyrics })
}
