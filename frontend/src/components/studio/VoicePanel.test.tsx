import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import VoicePanel from './VoicePanel'

/** SSR 冒烟：我的音色面板（FR-5）——合规口径（仅本人/活体/非采样）可见 */
describe('VoicePanel (FR-5)', () => {
  it('渲染注册入口与合规说明（默认 locale=en）', () => {
    const html = renderToString(<VoicePanel />)
    expect(html).toContain('My voice')
    expect(html).toContain('Enroll')
    expect(html).toContain('Two-random-phrase liveness check')
    expect(html).toContain('Own voice only')
    expect(html).toContain('not a neural speaker-verification model')
  })
})
