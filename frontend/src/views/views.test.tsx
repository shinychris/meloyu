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

  it('WorkDetailView 渲染加载态（无参数时不崩溃）', () => {
    const html = render(<WorkDetailView />)
    expect(html).toContain('加载中')
  })

  it('RightsView 渲染证书区与全局开关', () => {
    const html = render(<RightsView />)
    expect(html).toContain('每一首，都有清白凭证')
    expect(html).toContain('导出嵌入 AI 披露')
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
