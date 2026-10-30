import { useEffect, useRef, useState } from 'react'

/**
 * 锚点分区滚动高亮（ModelCenterView 与 SettingsView 共用，F-FE-09 抽取）：
 * 分区进入滚动视口上部区域时高亮对应导航项。
 * SSR/测试环境无 IntersectionObserver，防御性跳过。
 */
export function useScrollSpy(ids: readonly string[], rootMargin: string) {
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const [activeSection, setActiveSection] = useState(ids[0] ?? '')

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return
    const root = scrollRef.current
    if (!root) return
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting && e.target.id) setActiveSection(e.target.id)
        }
      },
      { root, rootMargin },
    )
    for (const id of ids) {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [ids, rootMargin])

  return { scrollRef, activeSection, setActiveSection }
}
