import { describe, expect, it } from 'vitest'
import { Suspense } from 'react'
import { renderToString } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import StudioView from './StudioView'
import LyricsView, { resolveDraftText } from './LyricsView'
import { lyricsEn } from '../i18n/en/lyrics'
import { lyricsZh } from '../i18n/zh/lyrics'
import { t, useI18nStore } from '../i18n'
import LibraryView from './LibraryView'
import RightsView from './RightsView'
import PricingView from './PricingView'
import WorkDetailView from './WorkDetailView'
import LoginView from './LoginView'
import EditView from './EditView'
import PitchView from './PitchView'
import ModelCenterView from './ModelCenterView'
import ResetPasswordView from './ResetPasswordView'
import SettingsView from './SettingsView'
import CandidateCard from '../components/studio/CandidateCard'
import DerivePanel from '../components/studio/DerivePanel'
import type { Candidate } from '../types/api'

function render(ui: React.ReactElement): string {
  return renderToString(<MemoryRouter>{ui}</MemoryRouter>)
}

function renderAt(path: string, ui: React.ReactElement): string {
  return renderToString(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>)
}

/** 渲染冒烟：保证每个视图 mount 时不会抛错（useEffect 在 SSR 不执行，不触发请求）；默认 locale=en 断言英文文案 */
describe('views render smoke', () => {
  it('LoginView 渲染登录表单与忘记密码入口（v0.13.0 起 demo 固定凭据提示已移除）', () => {
    const html = render(<LoginView />)
    expect(html).toContain('Sign in to Studio')
    expect(html).not.toContain('demo@meloyu.local')
    expect(html).toContain('Forgot password?')
  })

  it('StudioView 渲染四步引导与空状态', () => {
    const html = render(<StudioView />)
    expect(html).toContain('From one line to a release-ready song')
    expect(html).toContain('Describe ideas')
    expect(html).toContain('Generate 2 candidates')
  })

  it('LyricsView 渲染编辑器与按钮', () => {
    const html = render(<LyricsView />)
    expect(html).toContain('Write lyrics that lock to the melody')
    expect(html).toContain('Generate with AI')
    // F-04 回归：结构面板随编辑器内容实时解析（默认样例挂载即出各段行数，
    // 不再等首次生成响应才有结构数据）
    expect(html).toContain('Verse: 4 lines')
    expect(html).toContain('Pre-Chorus: 2 lines')
    expect(html).toContain('Outro: 0 lines')
  })

  it('LyricsView 默认样例跟随界面语言（v0.12.3：en 样例 → 切 zh 出中文样例）', () => {
    const enHtml = render(<LyricsView />)
    expect(enHtml).toContain('Piano fades in with rain')
    useI18nStore.setState({ locale: 'zh' })
    try {
      const zhHtml = render(<LyricsView />)
      expect(zhHtml).toContain('雨停在凌晨三点的窗台')
      expect(zhHtml).toContain('（轻声吟唱）')
      expect(zhHtml).not.toContain('Piano fades in with rain')
    } finally {
      useI18nStore.setState({ locale: 'en' })
    }
  })

  it('LibraryView 渲染表头与筛选 chips', () => {
    const html = render(<LibraryView />)
    expect(html).toContain('All works')
    expect(html).toContain('Trash')
  })

  it('LibraryView 搜索框为独立组件渲染（发现 #1：防抖不回写输入框）', () => {
    const html = render(<LibraryView />)
    expect(html).toContain('Search titles / lyrics…')
    expect(html).not.toContain('Clear search') // 初始为空：清空按钮不渲染（有内容时才出现）
  })

  it('WorkDetailView 渲染加载态（无参数时不崩溃）', () => {
    const html = render(<WorkDetailView />)
    expect(html).toContain('Loading')
  })

  it('RightsView 渲染证书区与授权说明（v0.7.0 摆设开关下架）', () => {
    const html = render(<RightsView />)
    expect(html).toContain('Every song comes with clean provenance')
    expect(html).toContain('Licensing notes')
    expect(html).toContain('Commercial rights follow the model license')
  })

  it('RightsView checklist 为真实数据驱动（P0-2 去虚还实）', () => {
    const html = render(<RightsView />)
    // AI 披露 = 真（证书真实能力）
    expect(html).toContain('AI generation disclosure written into every license certificate')
    // 内容指纹 = 真
    expect(html).toContain('SHA-256 fingerprint registered for every work')
    // 响度 = 灰色信息项（目标规格，非实测）
    expect(html).toContain('−14 LUFS is the export target spec, not measured per track')
    // 内容安全 = 黄点（基础敏感词过滤，如实）
    expect(html).toContain('Built-in basic sensitive-word filtering')
    // 三个摆设开关不再出现（任何语言）
    expect(html).not.toContain('Voice-clone dual verification')
    expect(html).not.toContain('人声克隆')
    expect(html).not.toContain('Inaudible watermark')
    expect(html).not.toContain('不可听水印')
  })

  it('PricingView 渲染激活加载态与流水表（v0.16.0 买断制；license 状态未就绪时显示加载）', () => {
    const html = render(<PricingView />)
    expect(html).toContain('One purchase, yours for life')
    // SSR 未加载态：license 为 null → Loading…
    expect(html).toContain('Loading…')
    // 订阅支付流组件已随 Stripe 拆除移除
    expect(html).not.toContain('Manage subscription')
    expect(html).not.toContain('Credit top-up pack')
  })

  it('SettingsView 渲染四分区设置页（v0.17.0：授权/用量统计收口到系统设置）', () => {
    const html = render(<SettingsView />)
    // 页头 + 四分区导航（SSR 快照为 store 初始态：license 未就绪时授权区局部加载，
    // 其余分区照常渲染——设置内容不被授权状态阻塞）
    expect(html).toContain('System settings')
    expect(html).toContain('General')
    expect(html).toContain('Usage &amp; analytics')
    expect(html).toContain('License')
    expect(html).toContain('Engines &amp; API')
    // 用量口径声明：单次买断、无官方积分消耗
    expect(html).toContain('No official credits are consumed')
    // 通用区：语言切换 + 引擎入口
    expect(html).toContain('Language')
    expect(html).toContain('English')
    expect(html).toContain('Open model center')
    // 授权分区文案（分区标题 + 加载态/词条齐备性）
    expect(html).toContain('Loading…')
    expect(t('license.trial.title')).toBe('Free trial')
    expect(t('license.trial.daysLeft', { n: 10 })).toBe('10 days left')
    expect(t('settings.general.edition.desktop')).toBe('Desktop (one-time license)')
  })

  it('ResetPasswordView 无 token 时提示链接无效；有 token 时渲染表单', () => {
    expect(renderAt('/reset-password', <ResetPasswordView />)).toContain(
      'This reset link is invalid or missing',
    )
    const form = renderAt('/reset-password?token=abc123', <ResetPasswordView />)
    expect(form).toContain('Set a new password')
    expect(form).toContain('Reset password')
  })

  it('/edit 与 /pitch 路由渲染真实视图（v0.11.0 占位转正）', () => {
    const editHtml = renderAt('/edit', <Suspense fallback={null}><EditView /></Suspense>)
    expect(editHtml).toContain('Waveform selection editing')
    const pitchHtml = renderAt('/pitch', <Suspense fallback={null}><PitchView /></Suspense>)
    expect(pitchHtml).toContain('Piano-roll note editing')
  })

  it('ModelCenterView 渲染本地组件中心（v0.16.0 桌面按需下载：内置/MusicGen/ACE-Step）', () => {
    const html = render(<ModelCenterView />)
    expect(html).toContain('Local component center')
    expect(html).toContain('Built-in synth engine')
    expect(html).toContain('On-device MusicGen')
    expect(html).toContain('On-device ACE-Step v1.5')
    // 如实标注：许可与硬件要求出现在组件卡上
    expect(html).toContain('CC-BY-NC')
    expect(html).toContain('8GB VRAM recommended')
  })

  it('ModelCenterView 渲染双引擎通道区（V1.3 歌词生成引擎）', () => {
    const html = render(<ModelCenterView />)
    expect(html).toContain('Lyrics engine channels')
    expect(html).toContain('Song generation engine channels')
    expect(html).toContain('External song API (Suno-compatible)')
    expect(html).toContain('BASE URL (Suno-compatible gateway root; /api/v1 is appended automatically)')
    expect(html).toContain('Test connection')
  })

  it('ModelCenterView 渲染开源歌曲模型目录区（V1.4 外部测评排序）', () => {
    const html = render(<ModelCenterView />)
    expect(html).toContain('Open-source song model catalog (ranked by third-party benchmarks)')
    expect(html).toContain('REPLICATE API TOKEN')
    expect(html).toContain('Replicate open-source model hosting')
    expect(html).toContain('On-device MusicGen (open source)')
  })

  it('ModelCenterView 渲染本机 ACE-Step 通道卡（V1.5 人声成曲）', () => {
    const html = render(<ModelCenterView />)
    expect(html).toContain('On-device ACE-Step v1.5 (open-source · vocal songs)')
    expect(html).toContain('Lyrics → full songs sung by realistic vocals')
  })

  it('ModelCenterView 渲染自托管服务通道卡（V1.5.1 MiniMax/SongGeneration）', () => {
    const html = render(<ModelCenterView />)
    expect(html).toContain('MiniMax Music 3')
    expect(html).toContain('SongGeneration')
  })

  it('ModelCenterView 左侧分类导航 + 生产就绪检查 + Ollama 服务地址（v0.12.0 重构）', () => {
    const html = render(<ModelCenterView />)
    // 左侧分类导航（六分区）
    for (const nav of ['Overview', 'Lyrics engine', 'Song engine', 'Open-source catalog',
      'Local model library', 'Operations']) {
      expect(html).toContain(nav)
    }
    // 生产就绪检查（settings 未加载前区块不渲染，导航文案仍在）
    expect(html).toContain('Lyrics engine channels')
    // Ollama 服务地址卡 + 通道分组标签
    expect(html).toContain('Ollama service address')
    expect(html).toContain('http://localhost:11434 (Docker deployment: http://host.docker.internal:11434)')
    expect(html).toContain('Cloud channels')
    expect(html).toContain('On-device GPU channels')
    expect(html).toContain('Self-hosted service channels')
    expect(html).toContain('Offline fallback (non-AI)')
    // 兜底通道明确标注非 AI
    expect(html).toContain('Offline rules engine (fallback)')
    expect(html).toContain('Offline synth engine (fallback)')
    expect(html).toContain('non-AI · fallback')
  })
})

/* ============ V1.1 候选派生操作（延长/变体/段落重生成） ============ */

const candidateFixture: Candidate = {
  id: 'c2f6b4e8d0a2468c9e1a3b5d7f9a1c3e',
  version_id: 'b8d4f2a6c1e34d5f908172635a4b7c9d',
  label: 'A',
  adopted: false,
  seed: 1832744110,
  quality_score: 92,
  duration_sec: 212,
  bpm: 90,
  key: { tonic: 'A', mode: 'minor' },
  time_signature: '4/4',
  vocal: 'female_air',
  language: 'zh',
  style_tags: ['华语流行'],
  structure: [
    { section: 'verse', bars: 11, start_bar: 0, start_sec: 0, end_sec: 29.3 },
    { section: 'chorus', bars: 11, start_bar: 11, start_sec: 29.3, end_sec: 58.7 },
    { section: 'chorus', bars: 11, start_bar: 22, start_sec: 58.7, end_sec: 88.1 },
  ],
  applied_negative: [],
  files: [],
  created_at: '2026-08-31T08:00:45Z',
}

describe('CandidateCard V1.1 派生操作', () => {
  it('延长/变体/段落重生成按钮可用，不再置灰 V1.1', () => {
    const html = render(
      <CandidateCard candidate={candidateFixture} index={0} workTitle="测试作品" modelLabel="V1 Pro" />,
    )
    expect(html).toContain('Extend')
    expect(html).toContain('Variant')
    expect(html).toContain('Regen section')
    expect(html).not.toContain('V1.1')
  })

  it('外部模型候选（quality_score=null）显示「外部模型」而非假质量分（V1.3）', () => {
    const external = { ...candidateFixture, quality_score: null }
    const html = render(
      <CandidateCard candidate={external} index={0} workTitle="测试作品" modelLabel="V1 Pro" />,
    )
    expect(html).toContain('External model')
    // 徽标本体不得出现数字分（tooltip 文案允许提及「AI 质量」）
    expect(html).not.toMatch(/AI quality \d/)
    expect(html).not.toContain('AI quality null')
  })

  it('送往编曲按钮渲染（v0.12.2：点击携带 work/version/candidate 上下文）', () => {
    const html = render(
      <CandidateCard candidate={candidateFixture} index={0} workTitle="测试作品" modelLabel="V1 Pro" />,
    )
    expect(html).toContain('Send to arrange')
  })
})

describe('DerivePanel 派生面板', () => {
  const noop = () => {}
  const base = {
    candidate: candidateFixture,
    busy: false,
    onSubmitExtend: noop,
    onSubmitVariant: noop,
    onSubmitRegen: noop,
    onClose: noop,
  }

  it('extend 面板渲染 15/30/60 秒预设', () => {
    const html = renderToString(<DerivePanel {...base} kind="extend" />)
    expect(html).toContain('+15s')
    expect(html).toContain('+30s')
    expect(html).toContain('+60s')
    expect(html).toContain('Extend 30s') // 默认选中 30
  })

  it('variant 面板渲染风格输入（可留空）', () => {
    const html = renderToString(<DerivePanel {...base} kind="variant" />)
    expect(html).toContain('leave blank = auto restyle')
    expect(html).toContain('Create variant')
  })

  it('regen 面板按 structure 列出段落，同名段落标注次序与起止秒', () => {
    const html = renderToString(<DerivePanel {...base} kind="regen" />)
    expect(html).toContain('Verse')
    expect(html).toContain('Chorus#1')
    expect(html).toContain('Chorus#2')
    expect(html).toContain('0:00–0:29')
    expect(html).toContain('0:59–1:28')
    // 未选段落时提交按钮禁用
    expect(html).toContain('disabled')
  })

  it('空 structure 时给出无法定位提示', () => {
    const html = renderToString(
      <DerivePanel {...base} kind="regen" candidate={{ ...candidateFixture, structure: [] }} />,
    )
    expect(html).toContain('No structure info for this candidate')
  })
})

/** v0.12.3：草稿解析三态——无草稿/样例草稿归样例态（跟随语言）/用户内容优先 */
describe('resolveDraftText（默认样例语言跟随）', () => {
  const enSample = lyricsEn['lyrics.defaultLyrics']
  const zhSample = lyricsZh['lyrics.defaultLyrics']

  it('无草稿 → null（样例态，显示当前语言样例）', () => {
    expect(resolveDraftText(null)).toBeNull()
  })

  it('历史草稿只是任一语言样例 → null（解锁语言锁死，跟随当前语言）', () => {
    expect(resolveDraftText(zhSample)).toBeNull()
    expect(resolveDraftText(enSample)).toBeNull()
  })

  it('用户编辑过的内容 → 原样保留，不被样例覆盖', () => {
    const mine = '[Verse]\n我自己写的词'
    expect(resolveDraftText(mine)).toBe(mine)
  })
})
