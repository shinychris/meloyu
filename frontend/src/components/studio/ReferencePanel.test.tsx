import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import ReferencePanel from './ReferencePanel'

/** SSR 冒烟：参考音频面板——权利确认门禁 + 合规文案可见 */
describe('ReferencePanel', () => {
  it('未勾选权利确认时上传按钮禁用，合规口径（非采样/权利）可见', () => {
    const html = renderToString(<ReferencePanel onClose={() => {}} />)
    expect(html).toContain('Choose an audio file') // 默认 locale=en
    expect(html).toContain('no waveform sampling')
    expect(html).toContain('hold the rights')
    const disabledBtn = html.match(/<button[^>]*disabled[^>]*>/g) ?? []
    expect(disabledBtn.length).toBeGreaterThan(0)
  })

  it('面板可关闭（关闭按钮 title=Close）', () => {
    const html = renderToString(<ReferencePanel onClose={() => {}} />)
    expect(html).toContain('title="Close"')
  })
})
