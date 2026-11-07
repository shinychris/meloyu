import { describe, expect, it } from 'vitest'
import {
  AUDIENCES,
  CAPABILITIES,
  CHANNELS,
  DEPLOY_LABEL,
  FAQS,
  INSPIRE_CHIPS,
  LANDING_METRICS,
  LANDING_VERSION,
  LICENSE_SKU,
  MODEL_CATALOG,
  SHOWCASE,
  WORKFLOW_STEPS,
} from './landing-data'
import { landingEn } from '../i18n/en/landing'
import { landingZh } from '../i18n/zh/landing'
import pkg from '../../package.json'

/** 双语言截图资产（shots/{en|zh}/*.png），glob 键为相对本文件的路径 */
const shotFiles = import.meta.glob('../../public/shots/*/*.png', {
  query: '?url',
  import: 'default',
  eager: true,
}) as Record<string, string>

/** 落地页数据完整性：对外口径的事实以 backend 为准，此处防止手改失真。
 *  文案字段已 key 化（landing.data.*），断言分两层：key 结构 + en 字典译文。 */
type LandingKey = keyof typeof landingEn
const enMap = landingEn as Record<string, string>
const zhMap = landingZh as Record<string, string>
const en = (k: string) => enMap[k]

describe('landing-data 落地页数据完整性', () => {
  it('LANDING_VERSION 与 package.json version 严格同步（v + version，防再脱节）', () => {
    expect(LANDING_VERSION).toBe(`v${pkg.version}`)
  })

  it('七通道齐备且字段完整（对齐 backend/app/providers/）', () => {
    expect(CHANNELS).toHaveLength(7)
    const ids = CHANNELS.map((c) => c.id)
    expect(new Set(ids).size).toBe(7)
    expect(ids).toEqual([
      'localsynth',
      'api',
      'replicate',
      'musicgen_local',
      'acestep_local',
      'mmax_local',
      'songgen_local',
    ])
    for (const c of CHANNELS) {
      expect(en(c.name), c.id).toBeTruthy()
      expect(en(c.highlight), c.id).toBeTruthy()
      expect(c.tags.length).toBeGreaterThanOrEqual(1)
      for (const tag of c.tags) expect(en(tag), `${c.id} tag`).toBeTruthy()
      expect(en(DEPLOY_LABEL[c.deploy]), c.deploy).toBeTruthy()
    }
  })

  it('部署方式覆盖四类', () => {
    const deploys = new Set(CHANNELS.map((c) => c.deploy))
    expect(deploys).toEqual(new Set(['local', 'cloud', 'selfhost', 'service']))
  })

  it('模型目录 10 项、按参考分降序、许可如实标注', () => {
    expect(MODEL_CATALOG).toHaveLength(10)
    const scores = MODEL_CATALOG.map((m) => m.score)
    expect([...scores].sort((a, b) => b - a)).toEqual(scores)
    for (const m of MODEL_CATALOG) {
      expect(en(m.license), m.name).toMatch(/MIT|Apache|CC-BY-NC|open|license|gated/i)
      expect(en(m.vendor), m.name).toBeTruthy()
      expect(m.maxDur).toMatch(/^\d+s$/)
    }
  })

  it('NC 许可模型不标记人声成曲能力（器乐如实）', () => {
    for (const m of MODEL_CATALOG) {
      if (en(m.license).includes('CC-BY-NC')) expect(m.vocals).toBe(false)
    }
  })

  it('授权卡为开源免费口径（MIT）：不含付费价格字段，功能清单完备（2026-11-06 起）', () => {
    expect(LICENSE_SKU.code).toBe('free')
    // 展示面不出现付费价格：价格字段必须移除（价格常量仅保留在 backend config 计费功能内）
    expect(Object.keys(LICENSE_SKU)).not.toContain('price')
    expect(Object.keys(LICENSE_SKU)).not.toContain('salePrice')
    expect(LICENSE_SKU.features.length).toBeGreaterThanOrEqual(5)
    const fields = [
      LICENSE_SKU.name,
      LICENSE_SKU.tagline,
      LICENSE_SKU.badge,
      LICENSE_SKU.platforms,
      ...LICENSE_SKU.features,
    ]
    for (const k of fields) expect(en(k), 'license field').toBeTruthy()
  })

  it('工作流四步与工作台 StepBar 一致', () => {
    expect(WORKFLOW_STEPS.map((s) => en(s.title))).toEqual([
      'Describe your idea',
      'Lyrics & structure',
      'Parameters & models',
      'Generate & refine',
    ])
    for (const s of WORKFLOW_STEPS) expect(en(s.desc), s.no).toBeTruthy()
  })

  it('展示区块数据非空且截图路径有效', () => {
    expect(CAPABILITIES).toHaveLength(6)
    expect(AUDIENCES).toHaveLength(3)
    expect(FAQS.length).toBeGreaterThanOrEqual(6)
    expect(LANDING_METRICS.length).toBe(5)
    expect(INSPIRE_CHIPS).toHaveLength(12)
    // src 为纯文件名，en/zh 双目录都必须有对应截图（英文界面零中文的截图面）
    for (const s of SHOWCASE) {
      expect(s.src).toMatch(/^[a-z]+\.png$/)
      for (const locale of ['en', 'zh']) {
        expect(shotFiles[`../../public/shots/${locale}/${s.src}`], `public/shots/${locale}/${s.src} missing`).toBeTruthy()
      }
    }
    for (const s of SHOWCASE) {
      expect(en(s.title)).toBeTruthy()
      expect(en(s.desc)).toBeTruthy()
    }
  })
})

describe('landing 字典双语完整性', () => {
  it('en 无中文残留（营销文案全部落地为英语）', () => {
    for (const [k, v] of Object.entries(landingEn)) {
      expect(v, k).toBeTruthy()
      expect(v, k).not.toMatch(/[\u4e00-\u9fff]/)
    }
  })

  it('zh 覆盖全部 key 且无空值', () => {
    for (const k of Object.keys(landingEn)) {
      expect(zhMap[k], k).toBeTruthy()
    }
  })

  it('zh 关键口径保持现有原文', () => {
    expect(zhMap['landing.data.license.name']).toBe('Meloyu 桌面版 · 开源免费')
    expect(zhMap['landing.data.step.1.title']).toBe('描述灵感')
    expect(zhMap['landing.data.faq.4.q']).toBe('生成的作品可以商用吗？')
    expect(zhMap['landing.data.channel.acestep_local.name']).toBe('本机 ACE-Step v1.5')
  })

  it('插值占位符在 en/zh 两侧一致', () => {
    const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',')
    const cases: LandingKey[] = [
      'landing.footer.meta',
      'landing.footer.copyright',
    ]
    for (const k of cases) {
      expect(placeholders(zhMap[k]), k).toBe(placeholders(enMap[k]))
      expect(placeholders(enMap[k]), k).not.toBe('')
    }
  })
})
