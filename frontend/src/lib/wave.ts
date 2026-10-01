/**
 * 波形自绘（复刻原型 drawWave：确定性伪随机条形）。
 * 原型即 canvas 自绘，不引入 wavesurfer 依赖。
 */
export function drawWave(canvas: HTMLCanvasElement, seed: number, color: string): void {
  const width = canvas.offsetWidth * 2 || 200
  const height = canvas.offsetHeight * 2 || 80
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, width, height)
  let s = seed || 1
  const rnd = () => {
    s = (s * 9301 + 49297) % 233280
    return s / 233280
  }
  const n = Math.max(8, Math.floor(width / 8))
  for (let i = 0; i < n; i++) {
    const bh = (0.22 + rnd() * 0.78) * height * 0.85
    ctx.fillStyle = i % 7 === 0 ? color : '#383838'
    ctx.fillRect(i * 8, (height - bh) / 2, 4, bh)
  }
}
