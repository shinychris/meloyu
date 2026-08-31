import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { debounce, sanitizeQuery } from './debounce'

/**
 * 搜索框防抖纯逻辑单测（模拟测试发现 #1 修复）：
 * 输入框即时 state 由组件本地持有，防抖只作用于 API 查询参数回调。
 */
describe('debounce', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('间隔内连续输入只触发一次，且取最后一次的值（Ctrl+A 替换场景）', () => {
    const calls: string[] = []
    const d = debounce((v: string) => calls.push(v), 400)
    d('国')
    vi.advanceTimersByTime(200)
    d('国风')
    vi.advanceTimersByTime(200)
    d('国风雨') // 全选替换后的最终值
    vi.advanceTimersByTime(399)
    expect(calls).toEqual([]) // 未到间隔不触发
    vi.advanceTimersByTime(1)
    expect(calls).toEqual(['国风雨'])
  })

  it('程序化清空：cancel 后丢弃待发值，不再触发', () => {
    const calls: string[] = []
    const d = debounce((v: string) => calls.push(v), 400)
    d('国风')
    d.cancel()
    vi.advanceTimersByTime(1000)
    expect(calls).toEqual([])
  })

  it('cancel 后可继续复用（清空后再输入仍正常防抖）', () => {
    const calls: string[] = []
    const d = debounce((v: string) => calls.push(v), 400)
    d('旧词')
    d.cancel()
    d('新词')
    vi.advanceTimersByTime(400)
    expect(calls).toEqual(['新词'])
  })

  it('cancel 幂等（组件卸载清理安全）', () => {
    const d = debounce((_v: string) => {}, 400)
    d('x')
    d.cancel()
    d.cancel()
    vi.advanceTimersByTime(1000)
  })
})

describe('sanitizeQuery（契约 §7.1：q ≤50 字）', () => {
  it('去除首尾空白', () => {
    expect(sanitizeQuery('  国风 ')).toBe('国风')
    expect(sanitizeQuery('   ')).toBe('')
  })

  it('超长输入截断到 50 字', () => {
    expect(sanitizeQuery('a'.repeat(80))).toHaveLength(50)
    expect(sanitizeQuery('a'.repeat(80))).toBe('a'.repeat(50))
  })
})
