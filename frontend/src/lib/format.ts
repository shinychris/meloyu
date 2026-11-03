import type { CreditReason, EventAction, PlanCode, Section, VocalType } from '../types/api'
import { t, type TranslationKey } from '../i18n'

/** 90 → "1:30" */
export function formatDuration(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec)) return '--:--'
  const s = Math.max(0, Math.round(sec))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** 92.4 → "1:32" */
export function formatClock(sec: number | null | undefined): string {
  return formatDuration(sec)
}

/** ISO → "2026-08-29 14:22:08"（本地时区；数字格式对 en/zh 通用，无需按 locale 变化） */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** 2468 → "2,468"（en-US 与 zh-CN 千分位规则一致） */
export function formatNum(n: number | null | undefined): string {
  if (n == null) return '—'
  return n.toLocaleString('en-US')
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/**
 * 以下标签函数按当前 locale 返回文案（app.format.* 命名空间）。
 * 原 PLAN_LABEL / SECTION_LABEL / VOCAL_LABEL 等常量表已改为函数，
 * 调用点由 `LABEL[x]` 改为 `xxxLabel(x)`。
 */
function label(keys: Record<string, TranslationKey>, value: string): string {
  return t(keys[value] ?? value)
}

const PLAN_KEYS: Record<PlanCode, TranslationKey> = {
  free: 'app.format.plan.free',
  pro: 'app.format.plan.pro',
  studio: 'app.format.plan.studio',
  team: 'app.format.plan.team',
}

export function planLabel(plan: PlanCode): string {
  return label(PLAN_KEYS, plan)
}

const SECTION_KEYS: Record<Section, TranslationKey> = {
  intro: 'app.format.section.intro',
  verse: 'app.format.section.verse',
  pre_chorus: 'app.format.section.pre_chorus',
  chorus: 'app.format.section.chorus',
  post_chorus: 'app.format.section.post_chorus',
  refrain: 'app.format.section.refrain',
  bridge: 'app.format.section.bridge',
  interlude: 'app.format.section.interlude',
  drop: 'app.format.section.drop',
  breakdown: 'app.format.section.breakdown',
  rap: 'app.format.section.rap',
  spoken: 'app.format.section.spoken',
  ad_lib: 'app.format.section.ad_lib',
  solo: 'app.format.section.solo',
  outro: 'app.format.section.outro',
}

export function sectionLabel(section: Section): string {
  return label(SECTION_KEYS, section)
}

const VOCAL_KEYS: Record<VocalType, TranslationKey> = {
  female_air: 'app.format.vocal.female_air',
  female_bright: 'app.format.vocal.female_bright',
  female_deep: 'app.format.vocal.female_deep',
  male_magnetic: 'app.format.vocal.male_magnetic',
  male_clear: 'app.format.vocal.male_clear',
  choir: 'app.format.vocal.choir',
  instrumental: 'app.format.vocal.instrumental',
  voice_clone: 'app.format.vocal.voice_clone',
}

export function vocalLabel(vocal: VocalType): string {
  return label(VOCAL_KEYS, vocal)
}

const CREDIT_KEYS: Record<CreditReason, TranslationKey> = {
  signup_bonus: 'app.format.credit.signup_bonus',
  generation: 'app.format.credit.generation',
  refund: 'app.format.credit.refund',
  plan_grant: 'app.format.credit.plan_grant',
  plan_switch: 'app.format.credit.plan_switch',
}

export function creditReasonLabel(reason: CreditReason): string {
  return label(CREDIT_KEYS, reason)
}

const EVENT_KEYS: Record<EventAction, TranslationKey> = {
  generate: 'app.format.event.generate',
  adopt: 'app.format.event.adopt',
  update: 'app.format.event.update',
  export: 'app.format.event.export',
  trash: 'app.format.event.trash',
  restore: 'app.format.event.restore',
  certificate: 'app.format.event.certificate',
  plan_switch: 'app.format.event.plan_switch',
}

export function eventActionLabel(action: EventAction): string {
  return label(EVENT_KEYS, action)
}

const ACTOR_KEYS: Record<string, TranslationKey> = {
  human: 'app.format.actor.human',
  ai: 'app.format.actor.ai',
  system: 'app.format.actor.system',
}

export function eventActorLabel(actor: string): string {
  return label(ACTOR_KEYS, actor)
}

/** 版本来源标签（source 枚举：generate/extend/variant/regen_section）；未知值原样显示 */
const SOURCE_KEYS: Record<string, TranslationKey> = {
  generate: 'app.format.source.generate',
  extend: 'app.format.source.extend',
  variant: 'app.format.source.variant',
  regen_section: 'app.format.source.regen_section',
}

export function versionSourceLabel(source: string): string {
  return label(SOURCE_KEYS, source)
}

/** 调性显示：{tonic:'A',mode:'minor'} → "A Minor" / "A 小调" */
export function keyLabel(key: { tonic: string; mode: string }): string {
  return `${key.tonic} ${t(key.mode === 'major' ? 'app.format.major' : 'app.format.minor')}`
}
