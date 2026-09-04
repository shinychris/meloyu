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
})
