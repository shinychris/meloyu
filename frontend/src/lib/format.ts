import type { CreditReason, EventAction, PlanCode, Section, VocalType } from '../types/api'

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

/** ISO → "2026-08-29 14:22:08"（本地时区） */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** 2468 → "2,468" */
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

export const PLAN_LABEL: Record<PlanCode, string> = {
  free: '免费',
  pro: '个人 Pro',
  studio: '创作人 Studio',
  team: '团队 / 企业',
}

export const SECTION_LABEL: Record<Section, string> = {
  intro: 'Intro',
  verse: 'Verse',
  pre_chorus: 'Pre',
  chorus: 'Chorus',
  bridge: 'Bridge',
  outro: 'Outro',
}

export const SECTION_ZH: Record<Section, string> = {
  intro: '前奏',
  verse: '主歌',
  pre_chorus: '导歌',
  chorus: '副歌',
  bridge: '桥段',
  outro: '尾奏',
}

export const VOCAL_LABEL: Record<VocalType, string> = {
  female_air: '女声 · 气声',
  female_bright: '女声 · 清亮',
  female_deep: '女声 · 浑厚',
  male_magnetic: '男声 · 磁性',
  male_clear: '男声 · 清朗',
  choir: '合唱',
  instrumental: '纯器乐',
}

export const CREDIT_REASON_LABEL: Record<CreditReason, string> = {
  signup_bonus: '注册赠送',
  generation: '生成消耗',
  refund: '失败退款',
  plan_grant: '档位发放',
  plan_switch: '档位切换',
}

export const EVENT_ACTION_LABEL: Record<EventAction, string> = {
  generate: '生成',
  adopt: '采用候选',
  update: '编辑作品',
  export: '导出',
  trash: '移入回收站',
  restore: '从回收站恢复',
  certificate: '下载证书',
  plan_switch: '切换档位',
}

export const EVENT_ACTOR_LABEL: Record<string, string> = {
  human: '人工',
  ai: 'AI',
  system: '系统',
}

/** 调性显示：{tonic:'A',mode:'minor'} → "A 小调" */
export function keyLabel(key: { tonic: string; mode: string }): string {
  return `${key.tonic} ${key.mode === 'major' ? '大调' : '小调'}`
}
