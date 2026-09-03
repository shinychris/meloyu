import { describe, expect, it } from 'vitest'
import { en } from './en'
import { zh } from './zh'

/**
 * i18n 字典完整性（双语硬性口径的防回归网）：
 * - en 全字典零中文（英语界面不允许出现任何中文）；
 * - zh 覆盖全部 key 且非空（中文界面不回退显示 key 或英文整句）；
 * - 插值占位符 en/zh 两侧一致（缺占位符会在运行时渲染出裸 "{n}"）。
 */
const zhRe = /[\u4e00-\u9fff]/
const enMap = en as unknown as Record<string, string>
const zhMap = zh as unknown as Record<string, string>

describe('i18n 字典完整性', () => {
  it('en 全字典值零中文', () => {
    const offenders = Object.entries(enMap).filter(([, v]) => zhRe.test(v))
    expect(offenders.map(([k, v]) => `${k}=${v}`)).toEqual([])
  })

  it('zh 覆盖全部 key 且无空值', () => {
    const missing = Object.keys(enMap).filter((k) => !zhMap[k])
    expect(missing).toEqual([])
  })

  it('插值占位符 en/zh 一致', () => {
    const ph = (s: string): string =>
      [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',')
    const bad = Object.keys(enMap)
      .filter((k) => ph(enMap[k]) !== ph(zhMap[k] ?? ''))
      .map((k) => `${k}: en[${ph(enMap[k])}] zh[${ph(zhMap[k] ?? '')}]`)
    expect(bad).toEqual([])
  })

  it('zh 值不含成句英文（允许术语/缩写：连续 4+ 个英文单词视为整句）', () => {
    const sentenceRe = /[A-Za-z]+ [a-z]+ [a-z]+ [a-z]+/
    const offenders = Object.entries(zhMap).filter(([, v]) => sentenceRe.test(v))
    expect(offenders.map(([k]) => k)).toEqual([])
  })
})
