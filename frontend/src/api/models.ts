import { apiGet, apiPost, apiPut } from './client'
import type {
  ExternalTestResult,
  LLMSettings,
  LLMSettingsUpdate,
  LocalModelsResult,
  ModelOpInfo,
  ModelsPresets,
  ModelsRuntime,
} from '../types/api'

/** GET /models/runtime —— Ollama 运行状态 + 当前生效引擎 */
export function getModelsRuntime(): Promise<ModelsRuntime> {
  return apiGet<ModelsRuntime>('/models/runtime')
}

/** GET /models/local —— 本地已装模型 + 进行中下载 + 推荐清单 */
export function getLocalModels(): Promise<LocalModelsResult> {
  return apiGet<LocalModelsResult>('/models/local')
}

/** GET /models/settings —— 歌词引擎通道配置（api_key 脱敏） */
export function getLLMSettings(): Promise<LLMSettings> {
  return apiGet<LLMSettings>('/models/settings')
}

/** PUT /models/settings —— 切换通道 / 更新连接配置 */
export function updateLLMSettings(patch: LLMSettingsUpdate): Promise<LLMSettings> {
  return apiPut<LLMSettings>('/models/settings', patch)
}

/** POST /models/pull —— 发起模型下载（202，轮询 ops/{id} 看进度） */
export function pullModel(model: string): Promise<ModelOpInfo> {
  return apiPost<ModelOpInfo>('/models/pull', { model })
}

/** POST /models/delete —— 删除本地模型（同步返回结果） */
export function deleteModel(model: string): Promise<ModelOpInfo> {
  return apiPost<ModelOpInfo>('/models/delete', { model })
}

/** GET /models/ops —— 最近模型操作记录 */
export function listModelOps(limit = 10): Promise<ModelOpInfo[]> {
  return apiGet<ModelOpInfo[]>('/models/ops', { limit })
}

/** GET /models/ops/{id} —— 下载进度轮询（1~2s） */
export function getModelOp(opId: string): Promise<ModelOpInfo> {
  return apiGet<ModelOpInfo>(`/models/ops/${opId}`)
}

/** POST /models/test-external —— 外部 API 连通性测试（不落库） */
export function testExternal(body: {
  base_url: string
  api_key: string
  model: string
}): Promise<ExternalTestResult> {
  return apiPost<ExternalTestResult>('/models/test-external', body)
}

/** POST /models/test-music —— 外部歌曲生成 API（Suno 兼容）探活（不落库，V1.3） */
export function testMusic(body: {
  base_url: string
  api_key: string
  model?: string
}): Promise<ExternalTestResult> {
  return apiPost<ExternalTestResult>('/models/test-music', body)
}

/** GET /models/presets —— 外部厂商预设 + 推荐 pull 清单 */
export function getModelsPresets(): Promise<ModelsPresets> {
  return apiGet<ModelsPresets>('/models/presets')
}
