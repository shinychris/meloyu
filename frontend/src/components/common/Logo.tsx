/** 品牌方格音符标（原 5 处内联 SVG 的统一组件，颜色走 --color-acc 令牌）。 */
export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 22 22" fill="none" aria-hidden="true">
      <rect x="1" y="1" width="20" height="20" stroke="var(--color-acc)" strokeWidth="2" />
      <rect x="6" y="9" width="3" height="7" fill="#ffffff" />
      <rect x="11" y="5" width="3" height="11" fill="var(--color-acc)" />
    </svg>
  )
}
