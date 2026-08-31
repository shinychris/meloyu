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
import CandidateCard from '../components/studio/CandidateCard'
import DerivePanel from '../components/studio/DerivePanel'
import type { Candidate } from '../types/api'

function render(ui: React.ReactElement): string {
  return renderToString(<MemoryRouter>{ui}</MemoryRouter>)
}

/** 渲染冒烟：保证每个视图 mount 时不会抛错（useEffect 在 SSR 不执行，不触发请求） */
describe('views render smoke', () => {
  it('LoginView 渲染登录表单与演示账号', () => {
    const html = render(<LoginView />)
    expect(html).toContain('登录工作台')
    expect(html).toContain('demo@meloyu.local')
  })

  it('StudioView 渲染四步引导与空状态', () => {
    const html = render(<StudioView />)
    expect(html).toContain('从一句描述，到可发行的歌')
    expect(html).toContain('描述灵感')
    expect(html).toContain('生成 2 个候选')
  })

  it('LyricsView 渲染编辑器与按钮', () => {
    const html = render(<LyricsView />)
    expect(html).toContain('写词，并与旋律对齐')
    expect(html).toContain('AI 生成歌词')
  })

  it('LibraryView 渲染表头与筛选 chips', () => {
    const html = render(<LibraryView />)
    expect(html).toContain('全部作品')
    expect(html).toContain('回收站')
  })

  it('LibraryView 搜索框为独立组件渲染（发现 #1：防抖不回写输入框）', () => {
    const html = render(<LibraryView />)
    expect(html).toContain('搜索标题 / 歌词…')
    expect(html).not.toContain('清空搜索') // 初始为空：清空按钮不渲染（有内容时才出现）
  })

  it('WorkDetailView 渲染加载态（无参数时不崩溃）', () => {
    const html = render(<WorkDetailView />)
    expect(html).toContain('加载中')
  })

  it('RightsView 渲染证书区与全局开关', () => {
    const html = render(<RightsView />)
    expect(html).toContain('每一首，都有清白凭证')
    expect(html).toContain('导出嵌入 AI 披露')
  })

  it('RightsView 合规检查文案不做失实断言（审查 P2-13）', () => {
    const html = render(<RightsView />)
    expect(html).toContain('导出目标规格（流媒体预设），非逐条实测')
    expect(html).toContain('SHA-256 指纹登记实现')
    expect(html).not.toContain('不可听水印已嵌入导出文件')
  })

  it('PricingView 渲染档位加载态与流水表', () => {
    const html = render(<PricingView />)
    expect(html).toContain('为创作付费，不为焦虑付费')
    expect(html).toContain('积分流水')
  })

  it('ComingSoonView 三个占位页都渲染', () => {
    expect(render(<ComingSoonView kind="arrange" />)).toContain('多轨时间线编曲')
    expect(render(<ComingSoonView kind="edit" />)).toContain('非破坏性音频剪辑')
    expect(render(<ComingSoonView kind="pitch" />)).toContain('旋律修调工坊')
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
    expect(html).toContain('延长')
    expect(html).toContain('变体')
    expect(html).toContain('段落重生成')
    expect(html).not.toContain('V1.1')
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
    expect(html).toContain('延长 30 秒') // 默认选中 30
  })

  it('variant 面板渲染风格输入（可留空）', () => {
    const html = renderToString(<DerivePanel {...base} kind="variant" />)
    expect(html).toContain('可留空 = 自动换风格')
    expect(html).toContain('生成变体')
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
    expect(html).toContain('该候选无结构信息，无法定位段落')
  })
})
