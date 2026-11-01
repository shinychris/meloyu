import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePlayerStore } from '../../stores/player'
import { formatDuration } from '../../lib/format'
import { useT } from '../../i18n'

/**
 * 68px 底部全局播放器：原生 <audio> 播放后端文件流（stream-token URL），
 * 进度条可点可拖、时间码、上一首/下一首、标题滚动 marquee。
 */
export default function TransportBar() {
  const t = useT()
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const navigate = useNavigate()
  const {
    current,
    playing,
    position,
    duration,
    bindAudio,
    toggle,
    next,
    prev,
    seekTo,
    onTimeUpdate,
    onLoadedMetadata,
    onEnded,
  } = usePlayerStore()

  useEffect(() => {
    bindAudio(audioRef.current)
    return () => bindAudio(null)
  }, [bindAudio])

  useEffect(() => {
    const el = audioRef.current
    if (!el) return
    const t = () => onTimeUpdate(el.currentTime)
    const m = () => onLoadedMetadata(el.duration)
    const pause = () => onTimeUpdate(el.currentTime)
    el.addEventListener('timeupdate', t)
    el.addEventListener('loadedmetadata', m)
    el.addEventListener('ended', onEnded)
    el.addEventListener('pause', pause)
    el.addEventListener('play', pause)
    return () => {
      el.removeEventListener('timeupdate', t)
      el.removeEventListener('loadedmetadata', m)
      el.removeEventListener('ended', onEnded)
      el.removeEventListener('pause', pause)
      el.removeEventListener('play', pause)
    }
  }, [onTimeUpdate, onLoadedMetadata, onEnded])

  const dur = duration || current?.durationSec || 0
  const pct = dur > 0 ? Math.min(100, (position / dur) * 100) : 0

  const seekFromEvent = (clientX: number, bar: HTMLElement) => {
    const rect = bar.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    seekTo(ratio * dur)
  }

  const onBarDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!current) return
    const bar = e.currentTarget
    seekFromEvent(e.clientX, bar)
    const move = (ev: MouseEvent) => seekFromEvent(ev.clientX, bar)
    const up = () => {
      document.removeEventListener('mousemove', move)
      document.removeEventListener('mouseup', up)
    }
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', up)
  }

  return (
    <footer className="fixed bottom-0 left-0 right-0 h-[68px] border-t flex items-center gap-3 px-3 sm:gap-4 sm:px-5 z-50 border-line bg-bg">
      <audio ref={audioRef} preload="metadata" />
      <div className="flex items-center gap-2">
        <button className="iconbtn" title={t('layout.player.prev')} onClick={() => void prev()}>
          <svg viewBox="0 0 16 16" fill="currentColor">
            <path d="M3 3h2v10H3zM13 3v10L6 8z" />
          </svg>
        </button>
        <button
          className={`iconbtn !w-10 !h-10 ${current ? 'on' : ''}`}
          style={current ? undefined : { borderColor: 'var(--acc)', color: 'var(--acc)' }}
          onClick={toggle}
          title={playing ? t('layout.player.pause') : t('layout.player.play')}
        >
          {playing ? (
            <svg viewBox="0 0 16 16" fill="currentColor">
              <path d="M4 3h3v10H4zM9 3h3v10H9z" />
            </svg>
          ) : (
            <svg viewBox="0 0 16 16" fill="currentColor">
              <path d="M5 3l8 5-8 5z" />
            </svg>
          )}
        </button>
        <button className="iconbtn" title={t('layout.player.next')} onClick={() => void next()}>
          <svg viewBox="0 0 16 16" fill="currentColor">
            <path d="M11 3h2v10h-2zM3 3v10l7-5z" />
          </svg>
        </button>
      </div>
      {/* 曲名区：窄屏隐藏（播放栏放不下，进度条与控制键优先） */}
      <div className={`w-[170px] min-w-0 hidden sm:block ${playing ? 'playing' : ''}`} style={{ visibility: current ? 'visible' : 'hidden' }}>
        <div className="text-sm font-semibold truncate marquee">
          <span>{current?.title ?? ''}</span>
        </div>
        <div className="text-2xs mt-0.5 truncate text-dim">
          {current?.subtitle ?? ''}
        </div>
      </div>
      <div className="flex-1 flex items-center gap-3">
        <span className="text-2xs num text-dim">
          {formatDuration(position)}
        </span>
        <div className="flex-1 h-[2px] relative cursor-pointer bg-line" onMouseDown={onBarDown}>
          <div
            className="absolute left-0 top-0 bottom-0 bg-acc"
            style={{ width: `${pct}%` }}
          ></div>
        </div>
        <span className="text-2xs num text-dim">
          {formatDuration(dur)}
        </span>
      </div>
      {/* 响度目标信息：窄屏隐藏（防止换行堆叠/挤出导出按钮），悬停有完整 title */}
      <div
        className="hidden md:flex items-center gap-2 text-2xs text-dim"
        title={t('layout.player.lufsTitle')}
      >
        <span>{t('layout.player.target')}</span>
        <span className="num text-acc">
          −14 LUFS
        </span>
        <span>·</span>
        <span className="num">−1.0 dBTP</span>
      </div>
      <button
        className="btn btn-ghost btn-sm"
        title={t('layout.player.exportTitle')}
        onClick={() => navigate('/library')}
      >
        {t('layout.player.export')}
      </button>
    </footer>
  )
}
