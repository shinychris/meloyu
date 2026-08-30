import type { Section } from '../types/api'

/** 结构标签（中英别名均可，与后端 synth/structure 解析规则保持一致的子集） */
const TAG_PATTERNS: Array<{ re: RegExp; section: Section }> = [
  { re: /^\[\s*(intro|前奏)\s*\]$/i, section: 'intro' },
  { re: /^\[\s*(verse|主歌)\s*\]$/i, section: 'verse' },
  { re: /^\[\s*(pre[-\s]?chorus|pre|导歌|预副歌)\s*\]$/i, section: 'pre_chorus' },
  { re: /^\[\s*(chorus|hook|副歌)\s*\]$/i, section: 'chorus' },
  { re: /^\[\s*(bridge|桥段|间奏)\s*\]$/i, section: 'bridge' },
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

/** 灵感指引组合 → 风格描述（复刻原型 composePrompt） */
export function composeStylePrompt(inspire: {
  scene: string
  mood: string
  genre: string
  inst: string
}): string {
  const parts = [
    inspire.genre,
    inspire.mood,
    inspire.inst ? `${inspire.inst}主导` : '',
    inspire.scene ? `适合${inspire.scene}` : '',
  ].filter(Boolean)
  return parts.join('，')
}
