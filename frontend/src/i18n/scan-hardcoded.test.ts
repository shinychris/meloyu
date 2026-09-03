import { describe, expect, it } from 'vitest'

/**
 * 组件层硬编码文案防回归网（v0.7.2 i18n 收口）：
 * - JSX 文本节点与展示属性（placeholder/title/aria-label/label/alt）里不允许
 *   出现中文（英文界面会直接显示）；
 * - 同位置不允许 ≥4 词的英文整句（中文界面会直接显示）——术语/缩写/型号除外。
 * 源码经 import.meta.glob(?raw) 读取（vitest 原生支持，无 node 依赖）。
 * i18n 目录跳过（字典自身另有 i18n.test.ts 全量校验）。
 */
const zhRe = /[\u4e00-\u9fff]/
const enSentenceRe = /[A-Za-z]+ [a-z]+ [a-z]+ [a-z]+/

const sources = import.meta.glob('../**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

describe('组件层硬编码文案', () => {
  it('JSX 文本/展示属性零中文、零英文整句', () => {
    const cjkHits: string[] = []
    const enHits: string[] = []
    for (const [path, code] of Object.entries(sources)) {
      const rel = path.replace(/^\.\//, '')
      if (rel.includes('/i18n/') || /\.test\./.test(rel)) continue
      const lines = (code as string).split('\n')
      lines.forEach((line: string, i: number) => {
        if (/^\s*(\/\/|\*|\/\*)/.test(line)) return // 注释行
        const check = (m: RegExpMatchArray, kind: string) => {
          const s = (m[1] ?? m[2] ?? '').trim()
          if (!s) return
          if (zhRe.test(s)) cjkHits.push(`${rel}:${i + 1} [${kind}] ${s}`)
          else if (enSentenceRe.test(s)) enHits.push(`${rel}:${i + 1} [${kind}] ${s}`)
        }
        for (const m of line.matchAll(
          /(?:placeholder|title|aria-label|label|alt)=\{?"([^"{}]+)"\}?/g)) check(m, 'prop')
        for (const m of line.matchAll(/>([A-Za-z][^<>{}]{3,60})</g)) check(m, 'jsx')
      })
    }
    expect(cjkHits, `英文界面将出现中文:\n${cjkHits.join('\n')}`).toEqual([])
    expect(enHits, `中文界面将出现英文整句:\n${enHits.join('\n')}`).toEqual([])
  })
})
