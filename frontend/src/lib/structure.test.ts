import { describe, expect, it, afterEach } from 'vitest'
import { composeStylePrompt, countParenMarks, countStructureTags, detectSectionAtCaret, insertAtCaret, parseSectionTag } from './structure'
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
  it('v0.12.1 新增段落（主流扩全）', () => {
    expect(parseSectionTag('[Post-Chorus]')).toBe('post_chorus')
    expect(parseSectionTag('[Post Chorus]')).toBe('post_chorus')
    expect(parseSectionTag('[Refrain]')).toBe('refrain')
    expect(parseSectionTag('[Interlude]')).toBe('interlude')
    expect(parseSectionTag('[间奏]')).toBe('interlude')
    expect(parseSectionTag('[Drop]')).toBe('drop')
    expect(parseSectionTag('[Breakdown]')).toBe('breakdown')
    expect(parseSectionTag('[Rap]')).toBe('rap')
    expect(parseSectionTag('[Rap Verse]')).toBe('rap')
    expect(parseSectionTag('[说唱]')).toBe('rap')
    expect(parseSectionTag('[Spoken]')).toBe('spoken')
    expect(parseSectionTag('[念白]')).toBe('spoken')
    expect(parseSectionTag('[Ad-Lib]')).toBe('ad_lib')
    expect(parseSectionTag('[adlib]')).toBe('ad_lib')
    expect(parseSectionTag('[Solo]')).toBe('solo')
    expect(parseSectionTag('[Guitar Solo]')).toBe('solo')
    expect(parseSectionTag('[Instrumental]')).toBe('solo')
    expect(parseSectionTag('[器乐段]')).toBe('solo')
  })
  it('带编号/连字符/下划线变体', () => {
    expect(parseSectionTag('[Verse 2]')).toBe('verse')
    expect(parseSectionTag('[Chorus 3]')).toBe('chorus')
    expect(parseSectionTag('[pre_chorus]')).toBe('pre_chorus')
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

describe('countParenMarks（括号表演标记统计，v0.12.3）', () => {
  it('中英括号均计数', () => {
    const lyrics = '[Verse]\n（轻声吟唱）雨停在凌晨三点的窗台\n（钢琴间奏）\nwe said it (soft)\n普通行'
    expect(countParenMarks(lyrics)).toBe(3)
  })
  it('无标记为 0', () => {
    expect(countParenMarks('[Verse]\n一行\n两行')).toBe(0)
  })
})

describe('insertAtCaret（光标处插入，v0.12.3）', () => {
  it('内联片段：光标处直接插入，返回新光标', () => {
    const [next, pos] = insertAtCaret('一行\n三行', 3, '（轻声）')
    expect(next).toBe('一行\n（轻声）三行')
    expect(next.slice(pos).startsWith('三行')).toBe(true)
  })
  it('整行片段：自动换行包裹', () => {
    const [next, pos] = insertAtCaret('[Verse]\n词', 9, '[Chorus]', { block: true })
    expect(next).toBe('[Verse]\n词\n[Chorus]\n')
    expect(pos).toBe(next.length)
  })
  it('光标在行中间时整行片段拆行不吞内容', () => {
    expect(insertAtCaret('[Verse]\n词', 8, '[Chorus]', { block: true })[0])
      .toBe('[Verse]\n[Chorus]\n词')
  })
  it('光标在行首/空文本时整行片段不重复换行', () => {
    expect(insertAtCaret('词一行', 0, '[Verse]', { block: true })[0]).toBe('[Verse]\n词一行')
    expect(insertAtCaret('', 0, '[Verse]', { block: true })[0]).toBe('[Verse]\n')
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
