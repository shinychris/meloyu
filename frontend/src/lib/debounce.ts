/**
 * 防抖与搜索词清洗（作品库搜索框，测试报告发现 #1 修复的配套纯逻辑）。
 *
 * 设计要点：防抖只作用于「对外通知（API 查询参数）」，输入框的即时 state
 * 由组件本地持有 —— 两者解耦后，防抖触发引起的列表重渲染不会再回写输入框，
 * Ctrl+A 全选替换与程序化清空得以保持原生行为。
 */

export interface Cancelable {
  cancel: () => void
}

/** 尾沿防抖：间隔内多次调用只在最后一次之后 ms 触发；返回带 cancel 的函数（组件卸载时清理） */
export function debounce<A extends unknown[]>(
  fn: (...args: A) => void,
  ms: number,
): ((...args: A) => void) & Cancelable {
  let timer: ReturnType<typeof setTimeout> | null = null
  let pending: A | null = null
  const wrapped = (...args: A): void => {
    pending = args
    if (timer != null) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      const call = pending
      pending = null
      if (call) fn(...call)
    }, ms)
  }
  wrapped.cancel = (): void => {
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
    pending = null
  }
  return wrapped
}

/** 搜索词清洗：trim + 截断（契约 §7.1 q ≤50 字） */
export function sanitizeQuery(value: string, max = 50): string {
  return value.trim().slice(0, max)
}
