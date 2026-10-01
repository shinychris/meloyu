const BARS = [
  { height: 8, color: 'var(--color-acc)' },
  { height: 5, color: 'var(--color-trk-vox)' },
  { height: 7, color: 'var(--color-trk-key)' },
  { height: 4, color: 'var(--color-trk-drm)' },
]

/** 等化器小记号：Landing 各区块 label 前的品牌母题（四竖条 = 四轨音色）。 */
export function EqMark({ className }: { className?: string }) {
  return (
    <span className={`inline-flex items-end gap-[2px] ${className ?? ''}`} style={{ height: 8 }} aria-hidden="true">
      {BARS.map((b, i) => (
        <span key={i} style={{ width: 2, height: b.height, background: b.color }} />
      ))}
    </span>
  )
}
