import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import StudioView from './StudioView'
import LyricsView from './LyricsView'
import LibraryView from './LibraryView'
import RightsView from './RightsView'
import PricingView from './PricingView'
import ComingSoonView from './ComingSoonView'
import WorkDetailView from './WorkDetailView'
import LoginView from './LoginView'
import ModelCenterView from './ModelCenterView'
import CandidateCard from '../components/studio/CandidateCard'
import DerivePanel from '../components/studio/DerivePanel'
import type { Candidate } from '../types/api'

function render(ui: React.ReactElement): string {
  return renderToString(<MemoryRouter>{ui}</MemoryRouter>)
}

/** 渲染冒烟：保证每个视图 mount 时不会抛错（useEffect 在 SSR 不执行，不触发请求）；默认 locale=en 断言英文文案 */
describe('views render smoke', () => {
  it('LoginView 渲染登录表单与演示账号', () => {
    const html = render(<LoginView />)
    expect(html).toContain('Sign in to Studio')
    expect(html).toContain('demo@meloyu.local')
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

  it('RightsView 渲染证书区与全局开关', () => {
    const html = render(<RightsView />)
    expect(html).toContain('Every song comes with clean provenance')
    expect(html).toContain('Embed AI disclosure on export')
  })

  it('RightsView 合规检查文案不做失实断言（审查 P2-13）', () => {
    const html = render(<RightsView />)
    expect(html).toContain('export target spec (streaming preset), not measured per track')
    expect(html).toContain('SHA-256 fingerprint registration')
    expect(html).not.toContain('watermark is embedded in exported files')
  })

  it('PricingView 渲染档位加载态与流水表', () => {
    const html = render(<PricingView />)
    expect(html).toContain('Pay for your craft, not your anxiety')
    expect(html).toContain('Credit transactions')
  })

  it('ComingSoonView 三个占位页都渲染', () => {
    expect(render(<ComingSoonView kind="arrange" />)).toContain('Multitrack timeline arranging')
    expect(render(<ComingSoonView kind="edit" />)).toContain('Non-destructive audio editing')
    expect(render(<ComingSoonView kind="pitch" />)).toContain('Melody tuning workshop')
  })

  it('ModelCenterView 渲染双引擎通道区（V1.3 歌曲生成引擎）', () => {
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
    expect(html).toContain('MiniMax Music 3 · self-hosted service')
    expect(html).toContain('SongGeneration · self-hosted service')
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
