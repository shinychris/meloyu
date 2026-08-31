/**
 * 与《API接口契约.md》v1.1 严格对齐的 TypeScript 类型（唯一事实来源的手写镜像）。
 * 字段名/可空性/枚举值不得偏离契约；联调发现差异以契约为准回改此文件。
 */

/* ============ 通用 ============ */
export interface ApiEnvelope<T> {
  code: number
  message: string
  data: T | null
  request_id: string
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/* ============ 枚举（契约 §1.5） ============ */
export type Mode = 'simple' | 'custom'
export type ModelId = 'v1_pro' | 'v1_fast'
export type Tonic = 'C' | 'C#' | 'D' | 'D#' | 'E' | 'F' | 'F#' | 'G' | 'G#' | 'A' | 'A#' | 'B'
export type KeyMode = 'major' | 'minor'
export type TimeSignature = '4/4' | '3/4' | '6/8'
export type VocalType =
  | 'female_air' | 'female_bright' | 'female_deep'
  | 'male_magnetic' | 'male_clear' | 'choir' | 'instrumental'
export type Language = 'zh' | 'yue' | 'en' | 'ja'
export type Section = 'intro' | 'verse' | 'pre_chorus' | 'chorus' | 'bridge' | 'outro'
export type PlanCode = 'free' | 'pro' | 'studio' | 'team'
export type TaskType = 'generation' | 'export'
export type TaskStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'
export type StageKey =
  | 'queued' | 'structure' | 'harmony' | 'melody' | 'arrange' | 'vocal' | 'mixdown' | 'serialize' | 'done'
export type CreditReason = 'signup_bonus' | 'generation' | 'refund' | 'plan_grant' | 'plan_switch'
export type EventAction = 'generate' | 'adopt' | 'update' | 'export' | 'trash' | 'restore' | 'certificate' | 'plan_switch'
export type EventActor = 'human' | 'ai' | 'system'
export type FileKind =
  | 'preview' | 'master' | 'stem' | 'midi'
  | 'export_mp3' | 'export_wav' | 'export_midi' | 'export_stems_zip' | 'certificate'
export type StemName = 'vocals' | 'drums' | 'bass' | 'other'
export type ExportFormat = 'mp3' | 'wav' | 'midi' | 'stems'
export type WorkStatus = 'active' | 'trash'
/** 版本来源（契约 §1.6：MVP 仅 generate，extend/variant/regen_section 为 V1.1 值） */
export type VersionSource = 'generate' | 'extend' | 'variant' | 'regen_section'

/* ============ 公共资源结构（契约 §1.6） ============ */
export interface CreditsInfo {
  balance: number
  monthly_grant: number
  carried_over: number
  next_grant_at: string
}

export interface User {
  id: string
  email: string
  nickname: string
  plan: PlanCode
  credits: CreditsInfo
  created_at: string
}

/** POST /auth/register 与 POST /auth/login 的 data */
export interface AuthData extends User {
  access_token: string
  token_type: 'Bearer'
  expires_in: number
}

export interface FileRef {
  file_id: string
  kind: FileKind
  stem_name: string | null
  name: string
  mime: string
  bytes: number
  duration_sec: number | null
}

export interface TaskError {
  code: number
  message: string
}

export interface CandidateSummary {
  id: string
  label: string
  quality_score: number
  duration_sec: number
  preview_file_id: string
}

export type TaskResult =
  | { candidates: CandidateSummary[] } // type=generation 且 succeeded
  | { files: FileRef[] } // type=export 且 succeeded

export interface Task {
  id: string
  type: TaskType
  status: TaskStatus
  format: ExportFormat | null
  progress: number
  stage_key: StageKey
  stage_label: string
  error: TaskError | null
  work_id: string | null
  version_id: string | null
  result: TaskResult | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface KeyInfo {
  tonic: Tonic
  mode: KeyMode
}

export interface StructureSegment {
  section: Section
  bars: number
  start_bar: number
  start_sec: number
  end_sec: number
}

export interface Candidate {
  id: string
  version_id: string
  label: string
  adopted: boolean
  seed: number
  quality_score: number
  duration_sec: number
  bpm: number
  key: KeyInfo
  time_signature: TimeSignature
  vocal: VocalType
  language: Language
  style_tags: string[]
  structure: StructureSegment[]
  applied_negative: string[]
  files: FileRef[]
  created_at: string
}

export interface Work {
  id: string
  display_code: string
  title: string
  status: WorkStatus
  favorite: boolean
  tags: string[]
  cover_color: string | null
  bpm: number
  key: KeyInfo
  duration_sec: number
  model: ModelId
  version_count: number
  active_version_id: string
  preview_file_id: string | null
  /**
   * 已成功导出的格式（去重，如 ['wav','mp3']）。V1.1 后端新增派生字段；
   * 后端未重启/旧数据时可能缺失，前端需回退推导（契约 §14 R1 / 审查 P2-5）。
   */
  exported_formats?: string[]
  created_at: string
  updated_at: string
  trashed_at: string | null
}

/** 生成请求 params 与版本快照 params 共用此形状（契约 §4.1 / §1.6） */
export interface GenerationParams {
  bpm: number
  key: KeyInfo
  time_signature: TimeSignature
  duration_sec: number
  vocal: VocalType
  language: Language
  instrument_density: number
}

export interface Version {
  id: string
  work_id: string
  parent_version_id: string | null
  version_no: string
  source: VersionSource
  active_candidate_id: string | null
  candidate_count: number
  params: GenerationParams
  lyrics: string
  created_at: string
}

export interface VersionTreeNode {
  id: string
  version_no: string
  parent_version_id: string | null
  source: VersionSource
  active_candidate_id: string | null
  candidate_count: number
  created_at: string
}

export interface VersionTreeData {
  current_version_id: string
  nodes: VersionTreeNode[]
}

export interface EditEvent {
  id: string
  work_id: string | null
  version_id: string | null
  task_id: string | null
  action: EventAction
  actor: EventActor
  detail: Record<string, unknown>
  created_at: string
}

export interface CreditTransaction {
  id: string
  delta: number
  reason: CreditReason
  ref_task_id: string | null
  balance_after: number
  created_at: string
}

export interface CreditsBalance {
  balance: number
  monthly_grant: number
  carried_over: number
  plan: PlanCode
  next_grant_at: string
}

/* ============ auth ============ */
export interface RegisterRequest {
  email: string
  password: string
  nickname: string
}

export interface LoginRequest {
  email: string
  password: string
}

/* ============ generations / tasks ============ */
export interface GenerationSubmitRequest {
  mode: Mode
  simple_prompt?: string
  style_prompt?: string
  lyrics?: string
  negative_prompt?: string
  model?: ModelId
  work_id?: string
  parent_version_id?: string
  simplified?: boolean
  seed?: number
  params?: GenerationParams
}

export interface GenerationSubmitResult {
  task: Task
  work: { id: string; display_code: string; title: string; cover_color: string | null }
  cost_credits: number
}

export interface CandidatesResult {
  items: Candidate[]
  inferred_structure: boolean
}

/* ============ V1.1 候选派生操作（契约 §5.5~5.7，响应复用 POST /generations 的 task+work 形态） ============ */

/** POST /candidates/{id}/extend —— 从结尾续写 seconds 秒（15~60），生成子版本 */
export interface ExtendCandidateRequest {
  seconds: number
}

/** POST /candidates/{id}/variant —— 同结构换风格生成子版本；style_prompt 缺省 = 自动换风格 */
export interface VariantCandidateRequest {
  style_prompt?: string
}

/**
 * POST /candidates/{id}/regen-section —— 仅重生成该段（其余段音频不变）。
 * 契约 v1.2 §5.7：请求体 { section, occurrence? }；occurrence 为该 section
 * 在候选 structure 中第几次出现，1 起始，缺省 = 1。
 */
export interface RegenSectionRequest {
  section: Section
  occurrence?: number
}

/* ============ lyrics ============ */
export interface LyricsGenerateRequest {
  theme: string
  style_hint?: string
  mood?: string | null
  language?: 'zh' | 'en'
  sections?: Section[]
}

export interface LyricsGenerateResult {
  lyrics: string
  structure: { section: Section; line_count: number }[]
  alternatives: { lyrics: string }[]
}

export interface LyricsPolishRequest {
  lyrics: string
  target_section?: Section
  style_hint?: string
  locked_lines?: number[]
}

export interface LyricsPolishResult {
  lyrics: string
  changes: { line_no: number; before: string; after: string }[]
  polished_sections: string[]
}

export interface RhymeLine {
  line_no: number
  text: string
  tail_char: string
  tail_pinyin: string
  rhyme_group: string
  in_rhyme: boolean
}

export interface RhymeCheckResult {
  sections: { section: Section; lines: RhymeLine[] }[]
  main_rhyme_group: string
  off_rhyme_count: number
  suggestions: { line_no: number; type: 'rhyme' | 'stress' | 'structure'; message: string }[]
}

export interface CompleteTagsResult {
  lyrics: string
  inferred: boolean
  detected: { section: Section; line_range: [number, number] }[]
}

/* ============ exports / files ============ */
export interface ExportRequest {
  version_id: string
  format: ExportFormat
}

export interface StreamTokenResult {
  url: string
  expires_in: number
}

/* ============ subscriptions ============ */
export interface PlanInfo {
  code: PlanCode
  name: string
  price_monthly: number | null
  price_yearly: number | null
  daily_generations: number | null
  monthly_credits: number | null
  max_export: string
  commercial_license: boolean
  watermark: boolean
  current: boolean
  features: string[]
}

export interface PlansResult {
  plans: PlanInfo[]
}

/* ============ system/meta ============ */
export interface Option {
  value: string
  label: string
}

export interface ModelMeta extends Option {
  value: ModelId
  credit_cost: number
  capabilities: { vocals: boolean; midi: boolean; stems: number }
}

export interface KeyOption {
  tonic: Tonic
  mode: KeyMode
  label: string
}

export interface StructureTag {
  tag: string
  section: Section
  label: string
}

export interface GenerationLimits {
  min_duration_sec: number
  max_duration_sec: number
  min_bpm: number
  max_bpm: number
  max_style_prompt: number
  max_lyrics: number
  max_negative_prompt: number
}

export interface InspirationMeta {
  scenes: string[]
  moods: string[]
  genres: string[]
  instruments: string[]
}

export interface SystemMeta {
  models: ModelMeta[]
  keys: KeyOption[]
  time_signatures: TimeSignature[]
  vocal_types: Option[]
  languages: Option[]
  structure_tags: StructureTag[]
  generation_limits: GenerationLimits
  inspiration: InspirationMeta
}

/* ============ 证书（§8.4，非包裹 JSON） ============ */
export interface Certificate {
  certificate_id: string
  work: { id: string; display_code: string; title: string }
  version: { id: string; version_no: string; active_candidate_id: string }
  model: { provider: string; provider_display: string; model: string; seed: number }
  generated_at: string
  license: { type: string; plan: PlanCode; valid: boolean }
  human_participation: { edit_events_count: number; summary: string[]; events_ref: string }
  fingerprint: { algorithm: string; master_wav_sha256: string; preview_mp3_sha256: string }
  disclosure: string
  issued_at: string
}

/* ============ works 查询参数 ============ */
export interface WorkListQuery {
  q?: string
  tag?: string
  favorite?: boolean
  status?: 'active' | 'trash' | 'all'
  sort?: 'updated_at' | 'created_at' | 'title'
  order?: 'desc' | 'asc'
  page?: number
  page_size?: number
}

export interface WorkPatchRequest {
  title?: string
  tags?: string[]
  favorite?: boolean
}

export interface WorkDeleteResult {
  deleted: boolean
  permanent: boolean
}
