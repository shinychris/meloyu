/** 浏览器端音频解码 → mono 22.05kHz 16bit wav（服务端零解码依赖的分析协议） */

export async function decodeToWav(data: ArrayBuffer): Promise<ArrayBuffer> {
  const Ctx =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  const ctx = new Ctx()
  try {
    const buf = await ctx.decodeAudioData(data.slice(0))
    const targetRate = 22050
    const off = new OfflineAudioContext(
      1,
      Math.max(1, Math.ceil(buf.duration * targetRate)),
      targetRate,
    )
    const src = off.createBufferSource()
    src.buffer = buf
    src.connect(off.destination)
    src.start()
    const rendered = await off.startRendering()
    const samples = rendered.getChannelData(0)
    const pcm = new Int16Array(samples.length)
    for (let i = 0; i < samples.length; i++) {
      const v = Math.max(-1, Math.min(1, samples[i]))
      pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff
    }
    const header = new ArrayBuffer(44)
    const dv = new DataView(header)
    const write = (o: number, str: string) => {
      for (let i = 0; i < str.length; i++) dv.setUint8(o + i, str.charCodeAt(i))
    }
    write(0, 'RIFF')
    dv.setUint32(4, 36 + pcm.length * 2, true)
    write(8, 'WAVE')
    write(12, 'fmt ')
    dv.setUint32(16, 16, true)
    dv.setUint16(20, 1, true)
    dv.setUint16(22, 1, true)
    dv.setUint32(24, targetRate, true)
    dv.setUint32(28, targetRate * 2, true)
    dv.setUint16(32, 2, true)
    dv.setUint16(34, 16, true)
    write(36, 'data')
    dv.setUint32(40, pcm.length * 2, true)
    const out = new Uint8Array(44 + pcm.length * 2)
    out.set(new Uint8Array(header), 0)
    out.set(new Uint8Array(pcm.buffer), 44)
    return out.buffer
  } finally {
    void ctx.close()
  }
}

/** 麦克风录音会话：start 后由调用方 stop（按短语句读完后停止），返回 wav 字节 */
export interface RecordingSession {
  stop: () => Promise<ArrayBuffer>
}

export async function startRecording(): Promise<RecordingSession> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const chunks: BlobPart[] = []
  const rec = new MediaRecorder(stream)
  rec.ondataavailable = (e) => {
    if (e.data.size > 0) chunks.push(e.data)
  }
  const stopped = new Promise<void>((resolve) => {
    rec.onstop = () => resolve()
  })
  rec.start()
  return {
    stop: async () => {
      rec.stop()
      await stopped
      stream.getTracks().forEach((tr) => tr.stop())
      const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' })
      return decodeToWav(await blob.arrayBuffer())
    },
  }
}
