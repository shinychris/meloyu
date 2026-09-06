import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import ArrangementView from './ArrangementView'

/** SSR 冒烟：多轨编辑器（V2）空态 + 关键文案 */
describe('ArrangementView (V2 editor)', () => {
  it('渲染空态引导与选择器（默认 locale=en）', () => {
    const html = renderToString(
      <MemoryRouter>
        <ArrangementView />
      </MemoryRouter>,
    )
    expect(html).toContain('Mix your stems, retune, save as a version')
    expect(html).toContain('Pick a work to start mixing')
    expect(html).toContain('Local-engine versions carry 4 stems')
  })

  it('带工作台上下文参数（?work=&version=&candidate=）SSR 不抛错（v0.12.2 送往编曲）', () => {
    const html = renderToString(
      <MemoryRouter initialEntries={['/arrange?work=w1&version=v1&candidate=c1']}>
        <ArrangementView />
      </MemoryRouter>,
    )
    expect(html).toContain('Mix your stems, retune, save as a version')
  })
})
