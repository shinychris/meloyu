import { afterEach, describe, expect, it } from 'vitest'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { http } from './client'
import {
  deleteModel,
  deployAceStep,
  getModelOp,
  getModelsRuntime,
  pullModel,
  testExternal,
  updateLLMSettings,
} from './models'

function mockAdapter(body: unknown, status = 200): AxiosAdapter {
  return (config: InternalAxiosRequestConfig) => {
    ;(config as unknown as { __last__: unknown }).__last__ = config
    return Promise.resolve({
      data: { code: 0, message: 'ok', data: body, request_id: 't' },
      status,
      statusText: 'ok',
      headers: {},
      config,
    } as AxiosResponse)
  }
}

/** 记录请求形态（method/url/body）供断言 */
let lastConfig: InternalAxiosRequestConfig | null = null
function recordingAdapter(body: unknown, status = 200): AxiosAdapter {
  const inner = mockAdapter(body, status)
  return (config) => {
    lastConfig = config
    return inner(config)
  }
}

afterEach(() => {
  lastConfig = null
})

describe('api/models 模型中心封装', () => {
  it('getModelsRuntime 解包运行时状态', async () => {
    http.defaults.adapter = recordingAdapter({
      ollama: { host: 'http://localhost:11434', running: true, version: '0.33.1',
        models_count: 5, error: '', install_hint: '' },
      active_backend: 'localsynth',
      engine: '本地规则引擎（离线可用）',
    })
    const rt = await getModelsRuntime()
    expect(rt.ollama.running).toBe(true)
    expect(rt.engine).toContain('本地规则')
    expect(lastConfig?.url).toBe('/models/runtime')
    expect(lastConfig?.method).toBe('get')
  })

  it('pullModel POST /models/pull 传 {model}', async () => {
    http.defaults.adapter = recordingAdapter({
      id: 'op123', op_type: 'pull', target: 'qwen3:0.6b', status: 'queued',
      progress: 0, message: '排队中', error_message: '', created_at: '', updated_at: '',
    }, 202)
    const op = await pullModel('qwen3:0.6b')
    expect(op.status).toBe('queued')
    expect(lastConfig?.url).toBe('/models/pull')
    expect(lastConfig?.method).toBe('post')
    expect(JSON.stringify((lastConfig as { data?: unknown })?.data)).toContain('qwen3:0.6b')
  })

  it('getModelOp 轮询路径带 op id', async () => {
    http.defaults.adapter = recordingAdapter({
      id: 'op123', op_type: 'pull', target: 'qwen3:0.6b', status: 'running',
      progress: 55, message: '下载中 55%', error_message: '', created_at: '', updated_at: '',
    })
    const op = await getModelOp('op123')
    expect(op.progress).toBe(55)
    expect(lastConfig?.url).toBe('/models/ops/op123')
  })

  it('deployAceStep POST /models/acestep-deploy（v0.16.3 组件应用内部署）', async () => {
    http.defaults.adapter = recordingAdapter({
      id: 'opd1', op_type: 'acestep_deploy', target: 'acestep', status: 'queued',
      progress: 0, message: '排队中', error_message: '', created_at: '', updated_at: '',
    }, 202)
    const op = await deployAceStep()
    expect(op.op_type).toBe('acestep_deploy')
    expect(lastConfig?.url).toBe('/models/acestep-deploy')
    expect(lastConfig?.method).toBe('post')
  })

  it('deleteModel / updateLLMSettings / testExternal 的方法与路径', async () => {
    const opBody = { id: 'x', op_type: 'delete', target: 'm', status: 'succeeded',
      progress: 100, message: '', error_message: '', created_at: '', updated_at: '' }
    http.defaults.adapter = recordingAdapter(opBody)
    await deleteModel('m')
    expect(lastConfig?.url).toBe('/models/delete')
    expect(lastConfig?.method).toBe('post')

    http.defaults.adapter = recordingAdapter({
      lyrics_backend: 'ollama', ollama_host: 'http://localhost:11434', ollama_model: 'qwen3.5:4b',
      external_base_url: '', external_model: '', external_api_key: { has_key: false, key_tail: '' },
    })
    await updateLLMSettings({ lyrics_backend: 'ollama', ollama_model: 'qwen3.5:4b' })
    expect(lastConfig?.url).toBe('/models/settings')
    expect(lastConfig?.method).toBe('put')

    http.defaults.adapter = recordingAdapter({ ok: true, sample: 'OK', message: '连接成功' })
    const r = await testExternal({ base_url: 'http://x/v1', api_key: 'k', model: 'm' })
    expect(r.ok).toBe(true)
    expect(lastConfig?.url).toBe('/models/test-external')
  })
})
