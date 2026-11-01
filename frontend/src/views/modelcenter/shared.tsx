import type {
  LyricsBackend,
  ModelOpInfo,
  MusicBackend,
  MusicCatalogModel,
} from '../../types/api'
import type { ReactNode } from 'react'
import { t, type TranslationKey } from '../../i18n'

/** 字节数 → 展示尺寸 */
export function fmtSize(bytes: number): string {
  if (!bytes) return '-'
  const gb = bytes / 1024 ** 3
  if (gb >= 1) return `${gb.toFixed(1)} GB`
  return `${Math.round(bytes / 1024 ** 2)} MB`
}

/** 左侧分类导航（锚点 + scrollspy 高亮） */
export const SECTIONS: { id: string; labelKey: TranslationKey }[] = [
  { id: 'mc-overview', labelKey: 'models.nav.overview' },
  { id: 'mc-components', labelKey: 'models.nav.components' },
  { id: 'mc-lyrics', labelKey: 'models.nav.lyrics' },
  { id: 'mc-music', labelKey: 'models.nav.music' },
  { id: 'mc-catalog', labelKey: 'models.nav.catalog' },
  { id: 'mc-library', labelKey: 'models.nav.library' },
  { id: 'mc-ops', labelKey: 'models.nav.ops' },
]

/** 通道元数据（按 id 查找；分组渲染见 LYRICS_GROUPS / MUSIC_GROUPS）。
 *  none=未配置：不可选（歌词创作必须有真实 LLM 通道，无兜底引擎——ADR-019），
 *  仅作为设置页/用量等处的通道展示名。 */
export const BACKENDS: Record<LyricsBackend, { title: TranslationKey; desc: TranslationKey }> = {
  none: { title: 'models.backend.none.title', desc: 'models.backend.none.desc' },
  ollama: { title: 'models.backend.ollama.title', desc: 'models.backend.ollama.desc' },
  openai_compat: { title: 'models.backend.openai_compat.title', desc: 'models.backend.openai_compat.desc' },
}

export const MUSIC_BACKENDS: Record<MusicBackend, { title: TranslationKey; desc: TranslationKey }> = {
  localsynth: { title: 'models.mbackend.localsynth.title', desc: 'models.mbackend.localsynth.desc' },
  acestep_local: { title: 'models.mbackend.acestep_local.title', desc: 'models.mbackend.acestep_local.desc' },
  mmax_local: { title: 'models.mbackend.mmax_local.title', desc: 'models.mbackend.mmax_local.desc' },
  songgen_local: { title: 'models.mbackend.songgen_local.title', desc: 'models.mbackend.songgen_local.desc' },
  replicate: { title: 'models.mbackend.replicate.title', desc: 'models.mbackend.replicate.desc' },
  api: { title: 'models.mbackend.api.title', desc: 'models.mbackend.api.desc' },
  musicgen_local: { title: 'models.mbackend.musicgen_local.title', desc: 'models.mbackend.musicgen_local.desc' },
}

/** 歌词引擎通道分组：真实模型通道（无兜底通道，未配置=none 不出卡） */
export const LYRICS_GROUPS: { labelKey: TranslationKey; items: LyricsBackend[]; fallback?: boolean }[] = [
  { labelKey: 'models.group.recommended', items: ['openai_compat', 'ollama'] },
]

/** 歌曲引擎通道分组：云端 / 本机 GPU / 自托管服务 / 离线兜底 */
export const MUSIC_GROUPS: { labelKey: TranslationKey; items: MusicBackend[]; fallback?: boolean }[] = [
  { labelKey: 'models.group.cloud', items: ['api', 'replicate'] },
  { labelKey: 'models.group.localGpu', items: ['acestep_local', 'musicgen_local'] },
  { labelKey: 'models.group.selfhosted', items: ['mmax_local', 'songgen_local'] },
  { labelKey: 'models.group.fallback', items: ['localsynth'], fallback: true },
]

/** 支持本机/自托管运行的通道（目录按钮/状态按此泛化渲染） */
export const LOCAL_CHANNELS: MusicBackend[] = ['acestep_local', 'musicgen_local', 'mmax_local', 'songgen_local']
/** 下载型本机通道（权重经模型中心下载）；其余本机通道为自托管服务型（端点可配） */
export const DOWNLOAD_CHANNELS: MusicBackend[] = ['acestep_local', 'musicgen_local']
export const localChannelOf = (m: MusicCatalogModel): MusicBackend | undefined =>
  m.channels.find((c) => LOCAL_CHANNELS.includes(c))

export const OP_TYPE_LABEL: Record<ModelOpInfo['op_type'], TranslationKey> = {
  pull: 'common.download', delete: 'common.delete', music_pull: 'common.download',
  music_delete: 'common.delete', acestep_deploy: 'models.comp.deploying',
}

/** 目录模型的本机状态文案（模块级翻译函数；组件经 useT 订阅语言变化后重渲染） */
export function localStatusText(m: MusicCatalogModel): { text: string; cls: string } {
  if (m.local_status === 'ready') return { text: t('models.status.ready'), cls: 'text-acc' }
  if (m.local_status === 'deps_missing') return { text: t('models.status.depsMissing'), cls: 'text-bad' }
  if (m.local_status === 'not_downloaded') return { text: t('models.status.notDownloaded'), cls: 'text-muted' }
  if (m.local_status === 'not_running') return { text: t('models.status.notRunning'), cls: 'text-bad' }
  return { text: t('models.status.hostedOnly'), cls: 'text-dim' }
}

/** 表单控件 token 类（与 index.css 表单基础规则同值，显式声明防漂移） */
export const inputCls = 'bg-bg border border-line text-txt outline-none'

/** 通道卡通用渲染（fallback 组弱化样式 + 「非 AI · 兜底」徽章） */
export function ChannelCard({ title, desc, on, onClick, fallback = false, children }: {
  title: TranslationKey
  desc: TranslationKey
  on: boolean
  onClick: () => void
  fallback?: boolean
  children?: ReactNode
}) {
  return (
    <div
      className={`card p-4 cursor-pointer transition-colors ${on ? '' : 'opacity-70 hover:opacity-100'}`}
      style={{
        // .card 未分层、优先级高于 utility：选中态描边/虚线只能用内联样式覆盖
        ...(on ? { borderColor: 'var(--acc)' } : {}),
        ...(fallback && !on ? { borderStyle: 'dashed' } : {}),
      }}
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <span className="text-base font-bold">{t(title)}</span>
        <span className="flex items-center gap-1.5">
          {fallback && <span className="badge badge-warn">{t('models.fallbackBadge')}</span>}
          <span className={`badge ${on ? 'badge-solid' : ''}`}>
            {on ? t('models.chan.inUse') : t('models.chan.select')}
          </span>
        </span>
      </div>
      <div className="text-xs mt-2 text-dim">{t(desc)}</div>
      {children}
    </div>
  )
}
