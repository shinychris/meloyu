import type { Section } from '../types/api'
import { getLocale } from '../i18n'

/** 结构标签（中英别名均可，与后端 synth/structure 解析规则保持一致的子集；
 *  顺序敏感：post-/pre-chorus 须排在 chorus 前，避免子串误匹配） */
const TAG_PATTERNS: Array<{ re: RegExp; section: Section }> = [
  { re: /^\[\s*(intro|前奏)\s*\]$/i, section: 'intro' },
  { re: /^\[\s*(verse\s?[1-4]?|主歌)\s*\]$/i, section: 'verse' },
  { re: /^\[\s*(pre[-_\s]?chorus|pre|导歌|预副歌)\s*\]$/i, section: 'pre_chorus' },
  { re: /^\[\s*(post[-_\s]?chorus|后副歌|副歌后)\s*\]$/i, section: 'post_chorus' },
  { re: /^\[\s*(chorus\s?[1-4]?|hook|副歌)\s*\]$/i, section: 'chorus' },
  { re: /^\[\s*(refrain|叠句)\s*\]$/i, section: 'refrain' },
  { re: /^\[\s*(bridge|桥段)\s*\]$/i, section: 'bridge' },
  { re: /^\[\s*(interlude|间奏)\s*\]$/i, section: 'interlude' },
  { re: /^\[\s*(drop|爆点)\s*\]$/i, section: 'drop' },
  { re: /^\[\s*(breakdown|分解段|崩解段)\s*\]$/i, section: 'breakdown' },
  { re: /^\[\s*(rap\s?verse|rapverse|rap|说唱段?|说唱)\s*\]$/i, section: 'rap' },
  { re: /^\[\s*(spoken\s?word|spoken|念白|独白)\s*\]$/i, section: 'spoken' },
  { re: /^\[\s*(ad[-_\s]?lib|adlib|即兴衬词|和声衬词)\s*\]$/i, section: 'ad_lib' },
  { re: /^\[\s*((guitar\s+)?solo|instrumental|独奏|器乐段)\s*\]$/i, section: 'solo' },
  { re: /^\[\s*(outro|尾奏)\s*\]$/i, section: 'outro' },
]

/** "[Verse]" → 'verse'；不匹配返回 null */
export function parseSectionTag(line: string): Section | null {
  const trimmed = line.trim()
  for (const { re, section } of TAG_PATTERNS) {
    if (re.test(trimmed)) return section
  }
  return null
}

/** 歌词中已识别的结构标签数（工作台「已识别 N 段结构标签」） */
export function countStructureTags(lyrics: string): number {
  const lines = lyrics.split('\n')
  let count = 0
  for (const line of lines) {
    if (parseSectionTag(line)) count++
  }
  return count
}

/** 括号表演标记统计（v0.12.3：中英括号成对内容，与后端 PAREN_MARK_RE 同口径） */
const PAREN_MARK_RE = /[（(][^（）()]{0,30}[）)]/g

export function countParenMarks(lyrics: string): number {
  return (lyrics.match(PAREN_MARK_RE) ?? []).length
}

/** 在光标处插入片段；返回 [新文本, 新光标位]。
 *  block=true（段落标签/整行标记）：确保片段独立成行，光标停在片段行末 */
export function insertAtCaret(
  text: string,
  caret: number,
  snippet: string,
  { block = false } = {},
): [string, number] {
  const head = text.slice(0, caret)
  const tail = text.slice(caret)
  if (!block) {
    return [head + snippet + tail, caret + snippet.length]
  }
  const headPad = !head || head.endsWith('\n') ? '' : '\n'
  const next = `${head}${headPad}${snippet}\n${tail}`
  return [next, head.length + headPad.length + snippet.length + 1]
}

/**
 * 光标所在段落（歌词助手「润色选中段」用）：
 * 从光标位置向前找最近一个结构标签行。
 */
export function detectSectionAtCaret(lyrics: string, caretIndex: number): Section | null {
  const before = lyrics.slice(0, caretIndex)
  const lines = before.split('\n')
  for (let i = lines.length - 1; i >= 0; i--) {
    const sec = parseSectionTag(lines[i])
    if (sec) return sec
  }
  return null
}

/** 灵感指引组合 → 风格描述（复刻原型 composePrompt）；按当前 locale 组合拼接词 */
export function composeStylePrompt(inspire: {
  scene: string
  mood: string
  genre: string
  inst: string
}): string {
  if (getLocale() === 'en') {
    return [
      inspire.genre,
      inspire.mood,
      inspire.inst ? `${inspire.inst}-led` : '',
      inspire.scene ? `great for ${inspire.scene}` : '',
    ].filter(Boolean).join(', ')
  }
  const parts = [
    inspire.genre,
    inspire.mood,
    inspire.inst ? `${inspire.inst}主导` : '',
    inspire.scene ? `适合${inspire.scene}` : '',
  ].filter(Boolean)
  return parts.join('，')
}
