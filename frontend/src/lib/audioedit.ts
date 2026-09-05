/**
 * 音频剪辑引擎（/edit，v0.11.0）：非破坏性操作模型 + 样本级渲染。
 *
 * 操作以 ops 数组描述（顺序应用），渲染永远从原始 AudioBuffer 重放——
 * 撤销/重做即回退 ops 快照，无损且确定（与 mixer.ts 的 Web Audio 图互补：
 * 本模块做时间域剪辑，mixdown 编码复用 mixer.encodeWav）。
 */

export type EditOpType = 'cut' | 'keep' | 'fadein' | 'fadeout' | 'gain' | 'normalize'

export interface EditOp {
  id: string
  type: EditOpType
  /** 作用区间（秒） */
  start: number
  end: number
  /** gain：分贝；normalize：目标峰值（0~1） */
  db?: number
  target?: number
}

export interface RenderedEdit {
  channels: Float32Array[]
  sampleRate: number
  duration: number
}

let opSeq = 0
export function nextOpId(): string {
  opSeq += 1
  return `op${opSeq}`
}

/** cut/keep 序列 → 保留段列表（秒，按序）。 */
function keepSegments(duration: number, ops: EditOp[]): Array<[number, number]> {
  let segs: Array<[number, number]> = [[0, duration]]
  for (const op of ops) {
    if (op.type === 'cut') {
      segs = segs.flatMap(([a, b]) => {
        if (op.end <= a || op.start >= b) return [[a, b] as [number, number]]
        const out: Array<[number, number]> = []
        if (op.start > a) out.push([a, op.start])
        if (op.end < b) out.push([op.end, b])
        return out
      })
    } else if (op.type === 'keep') {
      segs = segs.flatMap(([a, b]) => {
        const s = Math.max(a, op.start)
        const e = Math.min(b, op.end)
        return s < e ? [[s, e] as [number, number]] : []
      })
    }
  }
  return segs.filter(([a, b]) => b - a > 0.001)
}

/** 主渲染：从 src 重放全部 ops → 新声道数据（非破坏，可重复执行）。 */
export function renderEdit(src: AudioBuffer, ops: EditOp[]): RenderedEdit {
  const sr = src.sampleRate
  const duration = src.duration
  const segs = keepSegments(duration, ops)
  const nCh = src.numberOfChannels
  const chans: Float32Array[] = []
  for (let c = 0; c < nCh; c++) chans.push(src.getChannelData(c).slice())

  // 区间效果（淡入淡出/增益/标准化）：直接在（全量拷贝的）采样上施加，
  // 再按保留段裁剪——效果区间与段边界独立，语义直观
  for (const op of ops) {
    if (op.type === 'fadein' || op.type === 'fadeout') {
      const i0 = Math.max(0, Math.floor(op.start * sr))
      const i1 = Math.min(chans[0].length, Math.ceil(op.end * sr))
      const n = Math.max(1, i1 - i0)
      for (let c = 0; c < nCh; c++) {
        const ch = chans[c]
        for (let i = i0; i < i1; i++) {
          const p = (i - i0) / n
          const f = op.type === 'fadein' ? p : 1 - p
          ch[i] *= f
        }
      }
    } else if (op.type === 'gain' && op.db !== undefined) {
      const g = Math.pow(10, op.db / 20)
      const i0 = Math.max(0, Math.floor(op.start * sr))
      const i1 = Math.min(chans[0].length, Math.ceil(op.end * sr))
      for (let c = 0; c < nCh; c++) {
        for (let i = i0; i < i1; i++) chans[c][i] *= g
      }
    } else if (op.type === 'normalize') {
      const i0 = Math.max(0, Math.floor(op.start * sr))
      const i1 = Math.min(chans[0].length, Math.ceil(op.end * sr))
      let peak = 0
      for (let c = 0; c < nCh; c++) {
        for (let i = i0; i < i1; i++) peak = Math.max(peak, Math.abs(chans[c][i]))
      }
      const target = op.target ?? 0.99
      if (peak > 1e-6) {
        const g = target / peak
        for (let c = 0; c < nCh; c++) {
          for (let i = i0; i < i1; i++) chans[c][i] *= g
        }
      }
    }
  }

  // 裁剪保留段
  if (segs.length !== 1 || segs[0][0] !== 0 || segs[0][1] !== duration) {
    const total = segs.reduce((acc, [a, b]) => acc + Math.round(b * sr) - Math.round(a * sr), 0)
    const out: Float32Array[] = chans.map(() => new Float32Array(total))
    let w = 0
    for (const [a, b] of segs) {
      const i0 = Math.round(a * sr)
      const i1 = Math.round(b * sr)
      for (let c = 0; c < nCh; c++) out[c].set(chans[c].subarray(i0, i1), w)
      w += i1 - i0
    }
    chans.splice(0, chans.length, ...out)
  }
  return { channels: chans, sampleRate: sr, duration: chans[0].length / sr }
}

/** 爆音检测：|x| ≥ threshold 的采样占比与首例时间。 */
export function detectClips(buffer: AudioBuffer, threshold = 0.985): { count: number; firstSec: number | null; ratio: number } {
  const sr = buffer.sampleRate
  const n = buffer.length
  let count = 0
  let first: number | null = null
  for (let c = 0; c < buffer.numberOfChannels; c++) {
    const ch = buffer.getChannelData(c)
    for (let i = 0; i < n; i++) {
      if (Math.abs(ch[i]) >= threshold) {
        count++
        if (first === null) first = i / sr
      }
    }
  }
  return { count, firstSec: first, ratio: count / (n * buffer.numberOfChannels) }
}

/** 静音检测：|x| < 1e-4 的采样占比。 */
export function detectSilence(buffer: AudioBuffer): number {
  const n = buffer.length * buffer.numberOfChannels
  let silent = 0
  for (let c = 0; c < buffer.numberOfChannels; c++) {
    const ch = buffer.getChannelData(c)
    for (let i = 0; i < ch.length; i++) if (Math.abs(ch[i]) < 1e-4) silent++
  }
  return silent / n
}

/** RenderedEdit → AudioBuffer（离线上下文不可用时用普通上下文创建）。 */
export function toAudioBuffer(r: RenderedEdit): AudioBuffer {
  const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  const tmp = new Ctx()
  const buf = tmp.createBuffer(r.channels.length, r.channels[0].length, r.sampleRate)
  for (let c = 0; c < r.channels.length; c++) buf.copyToChannel(r.channels[c], c)
  void tmp.close()
  return buf
}

/** 峰值包络（波形绘制）。 */
export function peaksOf(buffer: AudioBuffer, buckets = 1200): number[] {
  const ch = buffer.getChannelData(0)
  const step = Math.max(1, Math.floor(ch.length / buckets))
  const out: number[] = []
  for (let i = 0; i < buckets; i++) {
    let peak = 0
    const s = i * step
    for (let j = s; j < Math.min(ch.length, s + step); j += 4) {
      const v = Math.abs(ch[j])
      if (v > peak) peak = v
    }
    out.push(peak)
  }
  return out
}
