import { create } from 'zustand'
import { getStreamToken } from '../api/files'
import { t } from '../i18n'
import { toast } from './toast'

export interface PlayerTrack {
  fileId: string
  title: string
  subtitle: string
  /** 展示用时长（秒），无则由 audio.loadedmetadata 提供 */
  durationSec: number | null
  /** 直连播放地址（公开资产用，如市场试听；设置后跳过 stream-token） */
  url?: string
}

/**
 * 全局播放器（单例 <audio> 挂在 TransportBar，状态在 store）。
 * 播放地址统一走 POST /files/{id}/stream-token（契约 §9.4，禁止 JWT 拼 URL）。
 */
interface PlayerState {
  current: PlayerTrack | null
  queue: PlayerTrack[]
  queueIndex: number
  playing: boolean
  position: number
  duration: number
  audio: HTMLAudioElement | null
  bindAudio: (el: HTMLAudioElement | null) => void
  /** 点任何列表的试听按钮都调这里：取 token → 设 src → 播放 */
  playTrack: (track: PlayerTrack) => Promise<void>
  toggle: () => void
  stop: () => void
  next: () => Promise<void>
  prev: () => Promise<void>
  seekTo: (sec: number) => void
  /** TransportBar 的 audio 事件回调 */
  onTimeUpdate: (sec: number) => void
  onLoadedMetadata: (dur: number) => void
  onEnded: () => void
}

function startPlayback(el: HTMLAudioElement) {
  el.play().catch(() => {
    toast(t('layout.player.autoplayBlocked'), 'warn')
  })
}

export const usePlayerStore = create<PlayerState>((set, get) => ({
  current: null,
  queue: [],
  queueIndex: -1,
  playing: false,
  position: 0,
  duration: 0,
  audio: null,

  bindAudio(el) {
    set({ audio: el })
  },

  async playTrack(track) {
    const { audio, current } = get()
    if (!audio) return
    if (current && current.fileId === track.fileId) {
      if (audio.paused) startPlayback(audio)
      else audio.pause()
      return
    }
    try {
      // 公开资产（市场试听）直连；私有文件走 stream-token（契约 §9.4，禁止 JWT 拼 URL）
      const url = track.url ?? (await getStreamToken(track.fileId)).url
      const el = get().audio
      if (!el) return
      const queue = [...get().queue]
      const existing = queue.findIndex((t) => t.fileId === track.fileId)
      let index: number
      if (existing >= 0) {
        index = existing
      } else {
        queue.push(track)
        index = queue.length - 1
      }
      el.src = url
      el.currentTime = 0
      // F-FE-14：playing 不得在 play() 落定前置 true——自动播放被拒时按钮
      // 会显示「暂停」却无声。play() resolve 后再置 true；catch 回置 false
      // 并提示（play/pause 事件经 TransportBar 同步兜底）。
      set({
        current: track,
        queue,
        queueIndex: index,
        position: 0,
        duration: track.durationSec ?? 0,
        playing: false,
      })
      try {
        await el.play()
        set({ playing: true })
      } catch {
        set({ playing: false })
        toast(t('layout.player.autoplayBlocked'), 'warn')
      }
    } catch {
      /* 拦截器已 toast（40401/40301 等） */
    }
  },

  toggle() {
    const { audio, current } = get()
    if (!audio || !current) {
      toast(t('layout.player.nothingToPlay'), 'warn')
      return
    }
    if (audio.paused) startPlayback(audio)
    else audio.pause()
  },

  stop() {
    const { audio } = get()
    if (audio) {
      audio.pause()
      audio.removeAttribute('src')
      audio.load()
    }
    set({ current: null, playing: false, position: 0, duration: 0, queueIndex: -1 })
  },

  async next() {
    const { queue, queueIndex } = get()
    if (queue.length === 0) {
      toast(t('layout.player.noNext'), 'warn')
      return
    }
    const idx = (queueIndex + 1) % queue.length
    await get().playTrack(queue[idx])
  },

  async prev() {
    const { queue, queueIndex } = get()
    if (queue.length === 0) {
      toast(t('layout.player.noPrev'), 'warn')
      return
    }
    const idx = (queueIndex - 1 + queue.length) % queue.length
    await get().playTrack(queue[idx])
  },

  seekTo(sec) {
    const { audio } = get()
    if (!audio) return
    audio.currentTime = sec
    set({ position: sec })
  },

  onTimeUpdate(sec) {
    set({ position: sec, playing: !get().audio?.paused })
  },

  onLoadedMetadata(dur) {
    if (dur > 0 && Number.isFinite(dur)) set({ duration: dur })
  },

  onEnded() {
    const { queue } = get()
    if (queue.length > 1) {
      void get().next()
    } else {
      set({ playing: false, position: 0 })
    }
  },
}))
