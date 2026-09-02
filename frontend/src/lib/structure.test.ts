import { describe, expect, it, afterEach } from 'vitest'
import { composeStylePrompt, countStructureTags, detectSectionAtCaret, parseSectionTag } from './structure'
import { useI18nStore } from '../i18n'

afterEach(() => {
  // 测试默认语言为 en；显式切过语言的用例恢复
  useI18nStore.setState({ locale: 'en' })
})

describe('parseSectionTag', () => {
  it('英文标签（大小写不敏感）', () => {
    expect(parseSectionTag('[Verse]')).toBe('verse')
    expect(parseSectionTag('[chorus]')).toBe('chorus')
    expect(parseSectionTag('  [Pre-Chorus]  ')).toBe('pre_chorus')
    expect(parseSectionTag('[Pre Chorus]')).toBe('pre_chorus')
    expect(parseSectionTag('[OUTRO]')).toBe('outro')
  })
  it('中文别名', () => {
    expect(parseSectionTag('[前奏]')).toBe('intro')
    expect(parseSectionTag('[主歌]')).toBe('verse')
    expect(parseSectionTag('[副歌]')).toBe('chorus')
    expect(parseSectionTag('[桥段]')).toBe('bridge')
  })
  it('非标签行返回 null', () => {
    expect(parseSectionTag('雨停在凌晨三点的窗台')).toBeNull()
    expect(parseSectionTag('[Verse')).toBeNull()
    expect(parseSectionTag('')).toBeNull()
    expect(parseSectionTag('[Unknown]')).toBeNull()
  })
})

describe('countStructureTags', () => {
  it('统计已有标签数', () => {
    const lyrics = '[Verse]\n一行\n两行\n[Chorus]\n三行\n[Outro]\n四行'
    expect(countStructureTags(lyrics)).toBe(3)
  })
  it('无标签为 0', () => {
    expect(countStructureTags('只是歌词\n没有标签')).toBe(0)
  })
})

describe('detectSectionAtCaret', () => {
  const lyrics = '[Verse]\n雨停在凌晨三点的窗台\n[Chorus]\n我们把未来说得太轻'

  it('光标在副歌行内 → chorus', () => {
    const caret = lyrics.indexOf('我们') + 2
    expect(detectSectionAtCaret(lyrics, caret)).toBe('chorus')
  })
  it('光标在主歌行内 → verse', () => {
    const caret = lyrics.indexOf('雨停') + 2
    expect(detectSectionAtCaret(lyrics, caret)).toBe('verse')
  })
  it('光标在第一个标签之前 → null', () => {
    expect(detectSectionAtCaret(lyrics, 0)).toBeNull()
  })
})

describe('composeStylePrompt（灵感指引组装）', () => {
  it('en 全选：genre, mood, X-led, great for scene', () => {
    expect(
      composeStylePrompt({ scene: 'Solo single', mood: 'Melancholy', genre: 'Mandopop', inst: 'Piano' }),
    ).toBe('Mandopop, Melancholy, Piano-led, great for Solo single')
  })
  it('en 部分选：跳过空项', () => {
    expect(composeStylePrompt({ scene: '', mood: 'Energetic', genre: 'EDM', inst: '' })).toBe('EDM, Energetic')
  })
  it('zh 全选：风格，情绪，乐器主导，适合场景', () => {
    useI18nStore.setState({ locale: 'zh' })
    expect(
      composeStylePrompt({ scene: '个人单曲', mood: '忧郁', genre: '华语流行', inst: '钢琴' }),
    ).toBe('华语流行，忧郁，钢琴主导，适合个人单曲')
  })
  it('zh 部分选：跳过空项', () => {
    useI18nStore.setState({ locale: 'zh' })
    expect(composeStylePrompt({ scene: '', mood: '热血', genre: 'EDM', inst: '' })).toBe('EDM，热血')
  })
  it('全空返回空串', () => {
    expect(composeStylePrompt({ scene: '', mood: '', genre: '', inst: '' })).toBe('')
  })
})
