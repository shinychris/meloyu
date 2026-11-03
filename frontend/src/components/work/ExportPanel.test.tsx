import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import ExportPanel from './ExportPanel'
import type { Work } from '../../types/api'

const work: Work = {
  id: 'w1',
  display_code: 'ML-0001',
  title: 'Rain Night Flight',
  status: 'active',
  favorite: false,
  tags: ['pop'],
  bpm: 96,
  key: { tonic: 'A', mode: 'minor' },
  duration_sec: 120,
  model: 'v1_pro',
  version_count: 1,
  created_at: '2026-09-04T00:00:00Z',
  updated_at: '2026-09-04T00:00:00Z',
  exported_formats: [],
} as unknown as Work

/** SSR 冒烟：发行导出预设区块渲染 + i18n 键存在性（en 默认 locale） */
describe('ExportPanel release presets', () => {
  it('渲染四格式 + 发行导出折叠区（副标题可见）', () => {
    const html = renderToString(<ExportPanel versionId="v1" work={work} />)
    expect(html).toContain('Export WAV')
    expect(html).toContain('Export MP3')
    expect(html).toContain('Release export')
    expect(html).toContain('Platform-ready package')
  })

  it('折叠区默认收起：平台选项与表单不渲染', () => {
    const html = renderToString(<ExportPanel versionId="v1" work={work} />)
    expect(html).not.toContain('Douyin Musician')
    expect(html).not.toContain('Build release package')
  })
})
