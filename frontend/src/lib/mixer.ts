/**
 * 多轨混音引擎（V2 编辑器 v0.9.0）：Web Audio 图——每轨
 * BufferSource → gain(音量/mute/solo) → 3 段 EQ（low shelf 200Hz / peaking 1kHz /
 * high shelf 4kHz）→ master gain → destination。
 *
 * 渲染回存：buildForRender 用 OfflineAudioContext(48k stereo) 复刻同一参数图
 * （确定性：节点参数由 state 唯一决定）→ wav bytes（POST /versions/{id}/mixdown）。
 */

export interface TrackParams {
  volume: number // 0~1.4
  muted: boolean
  solo: boolean
  eq: { low: number; mid: number; high: number } // dB
}

export interface MixerTrack {
  name: string
  buffer: AudioBuffer
  params: TrackParams
}

export const DEFAULT_PARAMS: TrackParams = {
  volume: 1,
  muted: false,
  solo: false,
  eq: { low: 0, mid: 0, high: 0 },
}

interface GraphNodes {
  source: AudioBufferSourceNode
  gain: GainNode
  low: BiquadFilterNode
  mid: BiquadFilterNode
  high: BiquadFilterNode
}

export class Mixer {
  private ctx: AudioContext
  private master: GainNode
  private nodes: GraphNodes[] = []
  private tracks: MixerTrack[] = []
  private startedAt = 0
  private offset = 0
  playing = false

  constructor() {
    const Ctx =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    this.ctx = new Ctx()
    this.master = this.ctx.createGain()
    this.master.connect(this.ctx.destination)
  }

  get currentTime(): number {
    if (!this.playing) return this.offset
    return this.offset + (this.ctx.currentTime - this.startedAt)
  }

  get duration(): number {
    return this.tracks.reduce((m, t) => Math.max(m, t.buffer.duration), 0)
  }

  load(tracks: MixerTrack[]): void {
    this.stop()
    this.tracks = tracks
  }

  private _chain(ctx: BaseAudioContext, track: MixerTrack, dest: AudioNode): GraphNodes {
    const source = ctx.createBufferSource()
    source.buffer = track.buffer
    const gain = ctx.createGain()
    const low = ctx.createBiquadFilter()
    low.type = 'lowshelf'
    low.frequency.value = 200
    const mid = ctx.createBiquadFilter()
    mid.type = 'peaking'
    mid.frequency.value = 1000
    mid.Q.value = 0.9
    const high = ctx.createBiquadFilter()
    high.type = 'highshelf'
    high.frequency.value = 4000
    source.connect(low).connect(mid).connect(high).connect(gain).connect(dest)
    return { source, gain, low, mid, high }
  }

  private _applyParams(nodes: GraphNodes, p: TrackParams, anySolo: boolean): void {
    const audible = !p.muted && (!anySolo || p.solo)
    nodes.gain.gain.value = audible ? p.volume : 0
    nodes.low.gain.value = p.eq.low
    nodes.mid.gain.value = p.eq.mid
    nodes.high.gain.value = p.eq.high
  }

  private _rebuild(): void {
    // 播放中参数变更：以当前 offset 重建图（简单可靠；轨道 ≤4 重建成本可忽略）
    const t = this.currentTime
    this.nodes.forEach((n) => {
      try {
        n.source.stop()
      } catch {
        /* 未启动过 */
      }
      n.source.disconnect()
    })
    this.nodes = this.tracks.map((tr) => this._chain(this.ctx, tr, this.master))
    this._syncParams()
    if (this.playing) {
      this._startFrom(t)
    } else {
      this.offset = t
    }
  }

  private _syncParams(): void {
    const anySolo = this.tracks.some((t) => t.params.solo)
    this.nodes.forEach((n, i) => this._applyParams(n, this.tracks[i].params, anySolo))
  }

  private _startFrom(sec: number): void {
    this.offset = Math.max(0, Math.min(sec, this.duration))
    this.startedAt = this.ctx.currentTime
    this.nodes.forEach((n) => {
      n.source.start(0, this.offset)
    })
  }

  async play(): Promise<void> {
    if (this.playing || this.tracks.length === 0) return
    await this.ctx.resume()
    if (this.nodes.length !== this.tracks.length) {
      this.nodes = this.tracks.map((tr) => this._chain(this.ctx, tr, this.master))
      this._syncParams()
    }
    this.playing = true
    this._startFrom(this.offset >= this.duration - 0.05 ? 0 : this.offset)
  }

  pause(): void {
    if (!this.playing) return
    this.offset = this.currentTime
    this.playing = false
    this.nodes.forEach((n) => {
      try {
        n.source.stop()
      } catch {
        /* ignore */
      }
    })
    this.nodes = []
  }

  stop(): void {
    this.pause()
    this.offset = 0
  }

  seek(sec: number): void {
    const wasPlaying = this.playing
    if (wasPlaying) this.pause()
    this.offset = Math.max(0, Math.min(sec, this.duration))
    if (wasPlaying) void this.play()
  }

  setParams(index: number, params: TrackParams): void {
    this.tracks[index].params = params
    if (this.nodes.length === this.tracks.length) {
      this._rebuild()
    }
  }

  close(): void {
    this.stop()
    void this.ctx.close()
  }

  /** 离线渲染当前混音状态 → wav 字节（48k stereo，供 mixdown 回存）。 */
  async buildForRender(): Promise<ArrayBuffer> {
    const sr = 48000
    const len = Math.max(1, Math.ceil(this.duration * sr))
    const off = new OfflineAudioContext(2, len, sr)
    const master = off.createGain()
    master.connect(off.destination)
    const anySolo = this.tracks.some((t) => t.params.solo)
    for (const tr of this.tracks) {
      const nodes = this._chain(off, tr, master)
      this._applyParams(nodes, tr.params, anySolo)
      nodes.source.start(0)
    }
    const rendered = await off.startRendering()
    return encodeWav(rendered)
  }
}

/** AudioBuffer → 16bit PCM wav（服务端解码重编码 master/preview）。 */
export function encodeWav(buffer: AudioBuffer): ArrayBuffer {
  const chs = Math.min(2, buffer.numberOfChannels)
  const len = buffer.length
  const pcm = new Int16Array(len * chs)
  const chans: Float32Array[] = []
  for (let c = 0; c < chs; c++) chans.push(buffer.getChannelData(c))
  for (let i = 0; i < len; i++) {
    for (let c = 0; c < chs; c++) {
      const v = Math.max(-1, Math.min(1, chans[c][i]))
      pcm[i * chs + c] = v < 0 ? v * 0x8000 : v * 0x7fff
    }
  }
  const header = new ArrayBuffer(44)
  const dv = new DataView(header)
  const w = (o: number, s: string) => {
    for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i))
  }
  const byteRate = buffer.sampleRate * chs * 2
  w(0, 'RIFF')
  dv.setUint32(4, 36 + pcm.length * 2, true)
  w(8, 'WAVE')
  w(12, 'fmt ')
  dv.setUint32(16, 16, true)
  dv.setUint16(20, 1, true)
  dv.setUint16(22, chs, true)
  dv.setUint32(24, buffer.sampleRate, true)
  dv.setUint32(28, byteRate, true)
  dv.setUint16(32, chs * 2, true)
  dv.setUint16(34, 16, true)
  w(36, 'data')
  dv.setUint32(40, pcm.length * 2, true)
  const out = new Uint8Array(44 + pcm.length * 2)
  out.set(new Uint8Array(header), 0)
  out.set(new Uint8Array(pcm.buffer), 44)
  return out.buffer
}

/** 波形峰值（canvas 绘制用，~1000 桶）。 */
export function peaksOf(buffer: AudioBuffer, buckets = 1000): number[] {
  const data = buffer.getChannelData(0)
  const size = Math.max(1, Math.floor(data.length / buckets))
  const out: number[] = []
  for (let i = 0; i < buckets; i++) {
    let peak = 0
    const start = i * size
    for (let j = start; j < Math.min(start + size, data.length); j += 4) {
      const v = Math.abs(data[j])
      if (v > peak) peak = v
    }
    out.push(peak)
  }
  return out
}
