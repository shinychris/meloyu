/**
 * 落地页展示数据（单一事实源）
 *
 * 全部为静态内嵌：落地页必须不依赖后端即可完整渲染。
 * 通道/模型目录与 backend/app/providers/music_catalog.py 对齐；
 * 定价与 backend/app/seed_data.py PLANS_ROWS 对齐；版本号取交付报告口径（v0.6.1）。
 *
 * i18n：所有用户可见文本字段值为字典 key（landing.data.*，见 src/i18n/en/landing.ts），
 * 类型即 TranslationKey，组件渲染处统一 t(field) 求值——语言切换即时生效，
 * 不在模块顶层按当前 locale 冻结一份译文。
 */
import type { TranslationKey } from '../i18n'

export const LANDING_VERSION = 'v0.6.1'

/** Hero 指标条 */
export const LANDING_METRICS: Array<{ value: string; label: TranslationKey }> = [
  { value: '7', label: 'landing.data.metric.channels' },
  { value: '10', label: 'landing.data.metric.models' },
  { value: '53', label: 'landing.data.metric.api' },
  { value: '145', label: 'landing.data.metric.smoke' },
  { value: '4', label: 'landing.data.metric.langs' },
]

/** 灵感 chips（与 /api/v1/system/meta 枚举一致，纯展示） */
export const INSPIRE_CHIPS: TranslationKey[] = [
  'landing.data.chip.1',
  'landing.data.chip.2',
  'landing.data.chip.3',
  'landing.data.chip.4',
  'landing.data.chip.5',
  'landing.data.chip.6',
  'landing.data.chip.7',
  'landing.data.chip.8',
  'landing.data.chip.9',
  'landing.data.chip.10',
  'landing.data.chip.11',
  'landing.data.chip.12',
]

/** 创作四步（与工作台 StepBar 一致） */
export const WORKFLOW_STEPS: Array<{ no: string; title: TranslationKey; desc: TranslationKey }> = [
  {
    no: '01',
    title: 'landing.data.step.1.title',
    desc: 'landing.data.step.1.desc',
  },
  {
    no: '02',
    title: 'landing.data.step.2.title',
    desc: 'landing.data.step.2.desc',
  },
  {
    no: '03',
    title: 'landing.data.step.3.title',
    desc: 'landing.data.step.3.desc',
  },
  {
    no: '04',
    title: 'landing.data.step.4.title',
    desc: 'landing.data.step.4.desc',
  },
]

/** 核心能力六卡 */
export const CAPABILITIES: Array<{
  icon: 'gen' | 'edit' | 'export' | 'lyrics' | 'rights' | 'engine'
  title: TranslationKey
  desc: TranslationKey
}> = [
  { icon: 'gen', title: 'landing.data.cap.1.title', desc: 'landing.data.cap.1.desc' },
  { icon: 'edit', title: 'landing.data.cap.2.title', desc: 'landing.data.cap.2.desc' },
  { icon: 'export', title: 'landing.data.cap.3.title', desc: 'landing.data.cap.3.desc' },
  { icon: 'lyrics', title: 'landing.data.cap.4.title', desc: 'landing.data.cap.4.desc' },
  { icon: 'rights', title: 'landing.data.cap.5.title', desc: 'landing.data.cap.5.desc' },
  { icon: 'engine', title: 'landing.data.cap.6.title', desc: 'landing.data.cap.6.desc' },
]

export type ChannelDeploy = 'local' | 'cloud' | 'selfhost' | 'service'

export const DEPLOY_LABEL: Record<ChannelDeploy, TranslationKey> = {
  local: 'landing.data.deploy.local',
  cloud: 'landing.data.deploy.cloud',
  selfhost: 'landing.data.deploy.selfhost',
  service: 'landing.data.deploy.service',
}

/** 七大生成通道（与 backend/app/providers/ 一一对应） */
export const CHANNELS: Array<{
  no: string
  id: string
  name: TranslationKey
  deploy: ChannelDeploy
  tags: TranslationKey[]
  highlight: TranslationKey
}> = [
  {
    no: '01',
    id: 'localsynth',
    name: 'landing.data.channel.localsynth.name',
    deploy: 'local',
    tags: [
      'landing.data.channel.localsynth.tag1',
      'landing.data.channel.localsynth.tag2',
      'landing.data.channel.localsynth.tag3',
    ],
    highlight: 'landing.data.channel.localsynth.hl',
  },
  {
    no: '02',
    id: 'api',
    name: 'landing.data.channel.api.name',
    deploy: 'cloud',
    tags: ['landing.data.channel.api.tag1', 'landing.data.channel.api.tag2'],
    highlight: 'landing.data.channel.api.hl',
  },
  {
    no: '03',
    id: 'replicate',
    name: 'landing.data.channel.replicate.name',
    deploy: 'cloud',
    tags: ['landing.data.channel.replicate.tag1', 'landing.data.channel.replicate.tag2'],
    highlight: 'landing.data.channel.replicate.hl',
  },
  {
    no: '04',
    id: 'musicgen_local',
    name: 'landing.data.channel.musicgen_local.name',
    deploy: 'selfhost',
    tags: [
      'landing.data.channel.musicgen_local.tag1',
      'landing.data.channel.musicgen_local.tag2',
      'landing.data.channel.musicgen_local.tag3',
    ],
    highlight: 'landing.data.channel.musicgen_local.hl',
  },
  {
    no: '05',
    id: 'acestep_local',
    name: 'landing.data.channel.acestep_local.name',
    deploy: 'selfhost',
    tags: [
      'landing.data.channel.acestep_local.tag1',
      'landing.data.channel.acestep_local.tag2',
      'landing.data.channel.acestep_local.tag3',
    ],
    highlight: 'landing.data.channel.acestep_local.hl',
  },
  {
    no: '06',
    id: 'mmax_local',
    name: 'landing.data.channel.mmax_local.name',
    deploy: 'service',
    tags: [
      'landing.data.channel.mmax_local.tag1',
      'landing.data.channel.mmax_local.tag2',
      'landing.data.channel.mmax_local.tag3',
    ],
    highlight: 'landing.data.channel.mmax_local.hl',
  },
  {
    no: '07',
    id: 'songgen_local',
    name: 'landing.data.channel.songgen_local.name',
    deploy: 'service',
    tags: [
      'landing.data.channel.songgen_local.tag1',
      'landing.data.channel.songgen_local.tag2',
      'landing.data.channel.songgen_local.tag3',
    ],
    highlight: 'landing.data.channel.songgen_local.hl',
  },
]

/** 开源模型目录（与 music_catalog.py 排序一致：外部测评参考分降序；name 为专有名词保持原文） */
export const MODEL_CATALOG: Array<{
  name: string
  vendor: TranslationKey
  score: number
  params: TranslationKey
  vocals: boolean
  maxDur: string
  license: TranslationKey
  note?: TranslationKey
}> = [
  {
    name: 'ACE-Step v1.5',
    vendor: 'landing.data.model.1.vendor',
    score: 9.3,
    params: 'landing.data.model.1.params',
    vocals: true,
    maxDur: '600s',
    license: 'landing.data.model.1.license',
    note: 'landing.data.model.1.note',
  },
  {
    name: 'MiniMax Music 3',
    vendor: 'landing.data.model.2.vendor',
    score: 8.8,
    params: 'landing.data.model.2.params',
    vocals: true,
    maxDur: '300s',
    license: 'landing.data.model.2.license',
  },
  {
    name: 'SongGeneration 2 / LeVo 2',
    vendor: 'landing.data.model.3.vendor',
    score: 8.7,
    params: 'landing.data.model.3.params',
    vocals: true,
    maxDur: '270s',
    license: 'landing.data.model.3.license',
  },
  {
    name: 'YuE',
    vendor: 'landing.data.model.4.vendor',
    score: 8.3,
    params: 'landing.data.model.4.params',
    vocals: true,
    maxDur: '240s',
    license: 'landing.data.model.4.license',
  },
  {
    name: 'Khala',
    vendor: 'landing.data.model.5.vendor',
    score: 8.2,
    params: 'landing.data.model.5.params',
    vocals: true,
    maxDur: '240s',
    license: 'landing.data.model.5.license',
  },
  {
    name: 'DiffRhythm',
    vendor: 'landing.data.model.6.vendor',
    score: 8.0,
    params: 'landing.data.model.6.params',
    vocals: true,
    maxDur: '240s',
    license: 'landing.data.model.6.license',
  },
  {
    name: 'MusicGen Large',
    vendor: 'landing.data.model.7.vendor',
    score: 7.8,
    params: 'landing.data.model.7.params',
    vocals: false,
    maxDur: '120s',
    license: 'landing.data.model.7.license',
  },
  {
    name: 'Stable Audio Open',
    vendor: 'landing.data.model.8.vendor',
    score: 7.2,
    params: 'landing.data.model.8.params',
    vocals: false,
    maxDur: '47s',
    license: 'landing.data.model.8.license',
  },
  {
    name: 'MusicGen Medium',
    vendor: 'landing.data.model.9.vendor',
    score: 7.2,
    params: 'landing.data.model.9.params',
    vocals: false,
    maxDur: '90s',
    license: 'landing.data.model.9.license',
  },
  {
    name: 'MusicGen Small',
    vendor: 'landing.data.model.10.vendor',
    score: 6.4,
    params: 'landing.data.model.10.params',
    vocals: false,
    maxDur: '60s',
    license: 'landing.data.model.10.license',
    note: 'landing.data.model.10.note',
  },
]

/** 目标用户三场景 */
export const AUDIENCES: Array<{ title: TranslationKey; sub: TranslationKey; points: TranslationKey[] }> = [
  {
    title: 'landing.data.audience.1.title',
    sub: 'landing.data.audience.1.sub',
    points: [
      'landing.data.audience.1.p1',
      'landing.data.audience.1.p2',
      'landing.data.audience.1.p3',
    ],
  },
  {
    title: 'landing.data.audience.2.title',
    sub: 'landing.data.audience.2.sub',
    points: [
      'landing.data.audience.2.p1',
      'landing.data.audience.2.p2',
      'landing.data.audience.2.p3',
    ],
  },
  {
    title: 'landing.data.audience.3.title',
    sub: 'landing.data.audience.3.sub',
    points: [
      'landing.data.audience.3.p1',
      'landing.data.audience.3.p2',
      'landing.data.audience.3.p3',
    ],
  },
]

/** 定价（与 seed_data.py PLANS_ROWS 对齐） */
export const PLANS: Array<{
  code: string
  name: TranslationKey
  monthly: number | null
  yearly: number | null
  tagline: TranslationKey
  features: TranslationKey[]
  popular?: boolean
}> = [
  {
    code: 'free',
    name: 'landing.data.plan.free.name',
    monthly: 0,
    yearly: 0,
    tagline: 'landing.data.plan.free.tagline',
    features: ['landing.data.plan.free.f1', 'landing.data.plan.free.f2', 'landing.data.plan.free.f3'],
  },
  {
    code: 'pro',
    name: 'landing.data.plan.pro.name',
    monthly: 58,
    yearly: 46,
    tagline: 'landing.data.plan.pro.tagline',
    features: ['landing.data.plan.pro.f1', 'landing.data.plan.pro.f2', 'landing.data.plan.pro.f3'],
  },
  {
    code: 'studio',
    name: 'landing.data.plan.studio.name',
    monthly: 168,
    yearly: 134,
    tagline: 'landing.data.plan.studio.tagline',
    features: [
      'landing.data.plan.studio.f1',
      'landing.data.plan.studio.f2',
      'landing.data.plan.studio.f3',
    ],
    popular: true,
  },
  {
    code: 'team',
    name: 'landing.data.plan.team.name',
    monthly: null,
    yearly: null,
    tagline: 'landing.data.plan.team.tagline',
    features: ['landing.data.plan.team.f1', 'landing.data.plan.team.f2', 'landing.data.plan.team.f3'],
  },
]

/** FAQ */
export const FAQS: Array<{ q: TranslationKey; a: TranslationKey }> = [
  { q: 'landing.data.faq.1.q', a: 'landing.data.faq.1.a' },
  { q: 'landing.data.faq.2.q', a: 'landing.data.faq.2.a' },
  { q: 'landing.data.faq.3.q', a: 'landing.data.faq.3.a' },
  { q: 'landing.data.faq.4.q', a: 'landing.data.faq.4.a' },
  { q: 'landing.data.faq.5.q', a: 'landing.data.faq.5.a' },
  { q: 'landing.data.faq.6.q', a: 'landing.data.faq.6.a' },
]

/** 界面一览（真机截图） */
export const SHOWCASE: Array<{ src: string; title: TranslationKey; desc: TranslationKey }> = [
  {
    src: '/shots/studio.png',
    title: 'landing.data.showcase.1.title',
    desc: 'landing.data.showcase.1.desc',
  },
  {
    src: '/shots/generating.png',
    title: 'landing.data.showcase.2.title',
    desc: 'landing.data.showcase.2.desc',
  },
]

/** 里程碑（交付报告口径） */
export const MILESTONES: Array<{ ver: string; date: string; title: TranslationKey }> = [
  { ver: 'v0.1.0', date: '2026-08', title: 'landing.data.milestone.1.title' },
  { ver: 'v0.2.0', date: '2026-08', title: 'landing.data.milestone.2.title' },
  { ver: 'v0.3.0', date: '2026-08', title: 'landing.data.milestone.3.title' },
  { ver: 'v0.4.0', date: '2026-08', title: 'landing.data.milestone.4.title' },
  { ver: 'v0.5.0', date: '2026-08', title: 'landing.data.milestone.5.title' },
  { ver: 'v0.6.0', date: '2026-08', title: 'landing.data.milestone.6.title' },
  { ver: 'v0.6.1', date: '2026-09', title: 'landing.data.milestone.7.title' },
]
