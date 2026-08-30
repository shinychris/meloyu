import { describe, expect, it } from 'vitest'
import {
  formatDuration,
  formatDateTime,
  formatNum,
  formatBytes,
  keyLabel,
  PLAN_LABEL,
} from './format'

describe('formatDuration', () => {
  it('秒数转 mm:ss', () => {
    expect(formatDuration(0)).toBe('0:00')
    expect(formatDuration(90)).toBe('1:30')
    expect(formatDuration(212)).toBe('3:32')
  })
  it('四舍五入', () => {
    expect(formatDuration(59.6)).toBe('1:00')
  })
  it('空值显示占位', () => {
    expect(formatDuration(null)).toBe('--:--')
    expect(formatDuration(undefined)).toBe('--:--')
  })
})

describe('formatDateTime', () => {
  it('ISO 转本地时间字符串', () => {
    const d = new Date(2026, 7, 29, 14, 22, 8)
    const iso = d.toISOString()
    const out = formatDateTime(iso)
    expect(out).toContain('2026-08-29')
    expect(out).toContain(':22:08')
  })
  it('空值', () => {
    expect(formatDateTime(null)).toBe('—')
    expect(formatDateTime(undefined)).toBe('—')
  })
})

describe('formatNum / formatBytes / keyLabel', () => {
  it('千分位', () => {
    expect(formatNum(2468)).toBe('2,468')
    expect(formatNum(0)).toBe('0')
    expect(formatNum(null)).toBe('—')
  })
  it('字节可读化', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB')
  })
  it('调性显示', () => {
    expect(keyLabel({ tonic: 'A', mode: 'minor' })).toBe('A 小调')
    expect(keyLabel({ tonic: 'C', mode: 'major' })).toBe('C 大调')
  })
  it('档位名称齐全', () => {
    for (const code of ['free', 'pro', 'studio', 'team'] as const) {
      expect(PLAN_LABEL[code].length).toBeGreaterThan(0)
    }
  })
})
