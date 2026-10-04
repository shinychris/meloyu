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
  /** FR-5（v0.8.2）：本人音色档案（须 voice_profile_id，仅本地引擎通道） */
  | 'voice_clone'
export type Language = 'zh' | 'yue' | 'en' | 'ja'
/** 段落枚举（契约 §1.5）：前 6 值 v1.1 既有，后 9 值 v1.20 扩全主流段落 */
export type Section =
  | 'intro' | 'verse' | 'pre_chorus' | 'chorus' | 'bridge' | 'outro'
  | 'post_chorus' | 'refrain' | 'interlude' | 'drop' | 'breakdown'
  | 'rap' | 'spoken' | 'ad_lib' | 'solo'
export type PlanCode = 'free' | 'pro' | 'studio' | 'team'
export type TaskType = 'generation' | 'export'
export type TaskStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'
export type StageKey =
  | 'queued' | 'writing' | 'structure' | 'harmony' | 'melody' | 'arrange' | 'vocal' | 'mixdown' | 'serialize' | 'done'
  /** 外部歌曲 API 通道阶段（V1.3）：提交/排队/生成中/下载 */
  | 'api_submit' | 'api_queue' | 'api_render' | 'api_download'
  /** 本机开源模型（MusicGen）通道阶段（V1.4） */
  | 'model_load' | 'model_sample' | 'model_export'
export type CreditReason = 'signup_bonus' | 'generation' | 'refund' | 'plan_grant' | 'plan_switch'
export type EventAction = 'generate' | 'adopt' | 'update' | 'export' | 'trash' | 'restore' | 'certificate' | 'plan_switch'
export type EventActor = 'human' | 'ai' | 'system'
export type FileKind =
  | 'preview' | 'master' | 'stem' | 'midi'
  | 'export_mp3' | 'export_wav' | 'export_midi' | 'export_stems_zip' | 'certificate'
export type StemName = 'vocals' | 'drums' | 'bass' | 'other'
export type ExportFormat = 'mp3' | 'wav' | 'midi' | 'stems' | 'release'
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

/** POST /auth/register 与 POST /auth/login 的 data（v0.13.0 起 refresh token 改经
 *  HttpOnly+SameSite=Strict Cookie 下发，不再出现在响应体；此处可选仅为兼容
 *  旧后端响应形状的解析，前端不消费） */
export interface AuthData extends User {
  access_token: string
  token_type: 'Bearer'
  expires_in: number
  refresh_token?: string
  refresh_expires_in?: number
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
  /** V1.3 起外部模型候选为 null（不产出 AI 质量分） */
  quality_score: number | null
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
  /** 执行引擎留痕（V1.3；V1.4 增 replicate/musicgen_local） */
  provider: 'localsynth' | 'api' | 'replicate' | 'musicgen_local' | null
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
  /** 外部模型候选仅有段落名与行数（V1.3，无本地小节网格） */
  line_count?: number
}

export interface Candidate {
  id: string
  version_id: string
  label: string
  adopted: boolean
  seed: number
  /** V1.3 起外部模型候选为 null（不产出 AI 质量分） */
  quality_score: number | null
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
  /** FR-13 协作上下文（详情接口在登录态返回；旧后端可能缺失） */
  space_id?: string | null
  is_owner?: boolean
  my_role?: 'owner' | 'editor' | 'commenter' | 'viewer' | null
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
  /** FR-5：vocal=voice_clone 时必填（已验证音色档案） */
  voice_profile_id?: string
  /** 哼唱成歌（v0.11.0）：[[相对半音, 拍长], ...]，仅本地引擎 */
  hum_melody?: number[][]
}

/* ============ voice-profiles（FR-5） ============ */
export interface VoiceProfile {
  id: string
  name: string
  status: 'pending' | 'verified' | 'rejected' | 'revoked'
  phrase1: string
  phrase2: string | null
  verify_score: number | null
  verify_attempts: number
  timbre: { center_midi: number; f1_scale: number; f2_scale: number; harm_scale: number; basis: string } | null
  consent_log: Array<{ step: number; phrase: string; sample_sha256: string; at: string; score?: number }>
  verified_at: string | null
  created_at: string
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
  /** 邮箱验证码（服务端开启 email_verification 时必填） */
  code?: string
}

export interface LoginRequest {
  email: string
  password: string
}

/* ============ v0.7.0 账号安全 / 数据自主 ============ */

/** POST /auth/forgot-password {email} —— 无论账号存在与否都返回 ok（防枚举） */
export interface ForgotPasswordRequest {
  email: string
}

/** POST /auth/reset-password {token, new_password}（token 来自邮件链接） */
export interface ResetPasswordRequest {
  token: string
  new_password: string
}

/** POST /auth/change-password（需 Bearer） */
export interface ChangePasswordRequest {
  old_password: string
  new_password: string
}

/** POST /auth/delete-account（需 Bearer；成功后前端清 token 跳落地页） */
export interface DeleteAccountRequest {
  password: string
}

export interface OkResult {
  ok: boolean
}

/* ============ v0.16.0 license（买断制激活，2026-10-03 定位转型） ============ */

/** GET /licenses/status —— 试用/激活状态（license 与 subscription 模式通用） */
export interface LicenseStatus {
  mode: 'cloud' | 'desktop' | 'enterprise'
  billing_mode: 'license' | 'subscription'
  trial: {
    started_at: string
    days: number
    days_left: number | null
    expires_at: string | null
    expired: boolean
  }
  activated: boolean
  license: {
    license_id: string
    tier: 'lifetime' | 'enterprise'
    devices: number
    account?: string | null
    note: string | null
    activated_at: string | null
  } | null
  device_id: string
  price_usd: number
  sale_price_usd: number
}

/** POST /licenses/activate 响应 = LicenseStatus */
export type LicenseActivateResult = LicenseStatus

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
  /** FR-4 参考音频：特征级参考（分析值覆盖 bpm/调性/器乐密度） */
  reference_track_id?: string
}

/* ============ 作品市场（V2-c） ============ */
export interface MarketListingInfo {
  id: string
  work_id: string
  title: string
  tags: string[]
  price_credits: number
  status: 'active' | 'delisted'
  preview_file_id: string | null
  seller: { user_id: string; nickname: string }
  sales: number
  created_at: string
}

export interface MarketOrderInfo {
  id: string
  listing_id: string
  work_id: string
  buyer_user_id: string
  seller_user_id: string
  price_credits: number
  seller_earnings: number
  platform_fee: number
  created_at: string
  /** 固定双语授权口径（非独占/不可转让/AIGC 署名保留） */
  license: string
}

/* ============ 开放 API 密钥（FR-19） ============ */
export interface ApiKeyInfo {
  id: string
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
}

/* ============ team spaces & comments（FR-13） ============ */
export type TeamRole = 'owner' | 'editor' | 'commenter' | 'viewer'

export interface TeamMemberInfo {
  user_id: string
  role: TeamRole
  created_at: string
}

export interface TeamSpaceInfo {
  id: string
  name: string
  owner_user_id: string
  is_owner: boolean
  my_role: TeamRole | null
  member_count: number
  work_count: number
  members: TeamMemberInfo[]
  created_at: string
}

export interface WorkCommentItem {
  id: string
  work_id: string
  version_id: string | null
  author_id: string
  author_nickname: string
  time_sec: number
  body: string
  resolved: boolean
  created_at: string
}

/* ============ reference-tracks（FR-4） ============ */
export interface ReferenceAnalysis {
  bpm: number
  key_tonic: Tonic
  key_mode: KeyMode
  energy: number
  brightness: number
  duration_sec: number
}

export interface ReferenceTrack {
  id: string
  name: string
  mime: string
  bytes: number
  duration_sec: number | null
  sha256: string
  ack_rights: boolean
  analysis: ReferenceAnalysis | null
  analyzed: boolean
  /** 合规提示（双语固定）：参考非采样 + 上传者权利确认 */
  notice: string
  created_at: string
}

export interface ReferenceTrackList {
  items: ReferenceTrack[]
  total: number
  page: number
  page_size: number
}

export interface GenerationSubmitResult {
  task: Task
  work: { id: string; display_code: string; title: string; cover_color: string | null }
  cost_credits: number
}

export interface CandidatesResult {
  items: Candidate[]
  inferred_structure: boolean
  /** 生成引擎署名（义务①：MiniMax 产出在生成结果页显著展示；v0.7.1） */
  provider: string
  provider_display: string
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
export interface PitchEditItem {
  beat: number
  semi: number
}

export interface PitchEditRequest {
  edits: PitchEditItem[]
  quantize: 'off' | '8' | '16'
}

export interface HumAnalysisData {
  notes: Array<{ start: number; dur: number; semi: number }>
  hum_melody: number[][]
  bpm_hint: number
  duration_sec: number
  note_count: number
  confidence: number
}

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
  /** V1.2：实际执行引擎（如 ollama:qwen3.5:4b / openai-compat:gpt-4o-mini） */
  engine?: string
  fallback?: boolean
  fallback_reason?: string
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
  engine?: string
  fallback?: boolean
  fallback_reason?: string
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
export interface ReleaseMeta {
  title: string
  artist: string
  album?: string
  explicit?: boolean
  language?: string
  genre?: string
  release_date?: string
  isrc?: string
  upc?: string
  lyrics_copyright?: string
  songwriter?: string
  /** 自定义封面（v0.11.0）：PNG base64（≥600²；缺省用系统占位图） */
  cover_png_b64?: string
}

export interface ExportRequest {
  version_id: string
  format: ExportFormat
  /** FR-11 发行导出预设：format=release 时必填 */
  platform?: 'douyin' | 'streaming'
  meta?: ReleaseMeta
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
  /** 团队版联系邮箱（env SALES_CONTACT_EMAIL；空=未配置不展示） */
  sales_contact?: string
  /** 价格币种（v0.14.0 起恒 'usd'；prices 为美分，展示侧除以 100） */
  currency?: string
  /** 充值积分包 SKU（后端 env 可调，前端不再硬编码） */
  topup?: { amount_usd: number; credits: number }
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
  /** 段落用途说明（v0.12.3 下发；旧后端可能缺省） */
  desc?: string
}

/** 括号表演标记词条（v0.12.3）：插入歌词描述演唱/情感/配器 */
export interface PerformanceMark {
  mark: string
  group: 'vocal' | 'music'
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
  performance_marks?: PerformanceMark[]
  generation_limits: GenerationLimits
  inspiration: InspirationMeta
  /** 注册邮箱验证码开关（SMTP 配置后开启；v0.10.2） */
  email_verification_enabled?: boolean
  /** 产品形态（v0.16.0 定位转型）：desktop=桌面单机 / enterprise=私有化 / cloud=存量云 */
  app_mode?: 'cloud' | 'desktop' | 'enterprise'
  billing_mode?: 'license' | 'subscription'
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

/* ============ models（V1.2 模型中心，契约 §5.8） ============ */
export type LyricsBackend = 'localsynth' | 'ollama' | 'openai_compat'

/** 歌曲生成引擎通道：本地合成 / Suno 兼容网关 / Replicate 托管 / 本机 MusicGen /
 *  本机 ACE-Step v1.5 / 自托管推理服务（MiniMax=SGLang-Omni、SongGeneration=Studio） */
export type MusicBackend =
  | 'localsynth' | 'api' | 'replicate' | 'musicgen_local' | 'acestep_local'
  | 'mmax_local' | 'songgen_local'

export interface OllamaRuntime {
  host: string
  running: boolean
  version: string
  models_count: number
  error: string
  install_hint: string
}

export interface ModelsRuntime {
  ollama: OllamaRuntime
  /** v0.12.0：后端是否运行在 Docker 容器内（loopback 地址自动改 host.docker.internal） */
  docker: boolean
  active_backend: LyricsBackend
  engine: string
  music_backend: MusicBackend
  song_engine: string
  replicate: { token_saved: boolean }
}

/** 开源歌曲模型目录项（V1.4，GET /models/music-catalog） */
export interface MusicCatalogModel {
  id: string
  name: string
  vendor: string
  license: string
  params: string
  capabilities: {
    vocals: boolean
    lyrics_input: boolean
    max_duration_sec: number
    languages: string
  }
  benchmark: { score: number; source: string; notes: string }
  channels: MusicBackend[]
  local_runnable: boolean
  local_hf_id: string | null
  local_size_mb: number
  local_note: string
  replicate_slug: string
  replicate_slug_default: string
  replicate_slug_overridden: boolean
  recommended: boolean
  recommend_reason: string
  rank: number
  local_status: 'not_applicable' | 'deps_missing' | 'not_downloaded' | 'not_running' | 'ready'
  /** 自托管服务型通道的探活详情（mmax_local/songgen_local 专属） */
  service_detail?: string
  selected: boolean
}

export interface MusicCatalog {
  models: MusicCatalogModel[]
  machine: {
    musicgen_deps_installed: boolean
    install_hint: string
    downloaded_ids: string[]
    acestep_deps_installed: boolean
    acestep_install_hint: string
    services: Record<string, { running: boolean; detail: string; hint: string; host: string }>
  }
  selected: { music_backend: MusicBackend; music_model: string | null }
  replicate: { token_saved: boolean }
  disclaimer: string
}

export interface LocalModelInfo {
  name: string
  size_bytes: number
  modified_at: string
  family: string
  parameter_size: string
  quantization: string
  capabilities: string[]
}

export interface RecommendedModel {
  tag: string
  name: string
  size_mb: number
  note: string
}

export interface ModelOpInfo {
  id: string
  /** V1.4 新增 music_pull/music_delete：开源歌曲模型（MusicGen）本地下载/删除 */
  op_type: 'pull' | 'delete' | 'music_pull' | 'music_delete'
  target: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  progress: number
  message: string
  error_message: string
  created_at: string
  updated_at: string
}

export interface LocalModelsResult {
  host: string
  models: LocalModelInfo[]
  selected: string
  pulling: ModelOpInfo[]
  error: string
  recommended: RecommendedModel[]
}

export interface LLMSettings {
  lyrics_backend: LyricsBackend
  ollama_host: string
  ollama_model: string
  external_base_url: string
  external_model: string
  external_api_key: { has_key: boolean; key_tail: string }
  music_backend: MusicBackend
  music_api_base_url: string
  music_api_model: string
  music_api_key: { has_key: boolean; key_tail: string }
  /** V1.4：开源歌曲模型目录当前选用（如 ace-step / musicgen-small） */
  music_model: string
  /** V1.4：Replicate Token（脱敏；显式空串=清除） */
  replicate_api_token: { has_key: boolean; key_tail: string }
  replicate_slugs: Record<string, string>
  /** 自托管推理服务端点（mmax_local/songgen_local → base_url，V1.5.1） */
  local_service_hosts: Record<string, string>
}

export interface LLMSettingsUpdate {
  lyrics_backend?: LyricsBackend
  ollama_host?: string
  ollama_model?: string
  external_base_url?: string
  external_model?: string
  /** 空串/省略 = 保持不变（脱敏读回无法回显） */
  external_api_key?: string
  music_backend?: MusicBackend
  music_api_base_url?: string
  music_api_model?: string
  music_api_key?: string
  /** V1.4：目录模型 id（后端按模型通道自动推断 music_backend） */
  music_model?: string
  /** V1.4：显式空串 = 清除 Token */
  replicate_api_token?: string
  replicate_slugs?: Record<string, string>
  local_service_hosts?: Record<string, string>
}

export interface ExternalTestResult {
  ok: boolean
  sample: string
  message: string
}

/** 外部歌曲生成 API 厂商预设（GET /models/presets，V1.3） */
export interface MusicApiPreset {
  vendor: string
  base_url: string
  model_hint: string
}

export interface ExternalPreset {
  vendor: string
  base_url: string
  model_hint: string
}

export interface ModelsPresets {
  external_presets: ExternalPreset[]
  music_api_presets: MusicApiPreset[]
  recommended_models: RecommendedModel[]
}
