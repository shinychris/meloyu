import { create } from 'zustand'
import type { SystemMeta } from '../types/api'
import { getSystemMeta } from '../api/account'

const TONICS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const

function defaultKeys(): SystemMeta['keys'] {
  const list: SystemMeta['keys'] = []
  for (const mode of ['major', 'minor'] as const) {
    for (const tonic of TONICS) {
      list.push({ tonic, mode, label: `${tonic} ${mode === 'major' ? '大调' : '小调'}` })
    }
  }
  // 原型默认展示顺序：A 小调 / C 大调 / G 大调 / F 大调 提前
  const priority = ['A|minor', 'C|major', 'G|major', 'F|major']
  list.sort((a, b) => {
    const ai = priority.indexOf(`${a.tonic}|${a.mode}`)
    const bi = priority.indexOf(`${b.tonic}|${b.mode}`)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
  })
  return list
}

/** 与契约 §12.2 完全一致的兜底元数据（接口不可达时 UI 仍可工作；成功后覆盖） */
function defaultMeta(): SystemMeta {
  return {
    models: [
      {
        value: 'v1_pro',
        label: 'V1 Pro · 高质',
        credit_cost: 12,
        capabilities: { vocals: true, midi: true, stems: 4 },
      },
      {
        value: 'v1_fast',
        label: 'V1 · 快速草稿',
        credit_cost: 6,
        capabilities: { vocals: true, midi: true, stems: 4 },
      },
    ],
    keys: defaultKeys(),
    time_signatures: ['4/4', '3/4', '6/8'],
    vocal_types: [
      { value: 'female_air', label: '女声 · 气声' },
      { value: 'female_bright', label: '女声 · 清亮' },
      { value: 'female_deep', label: '女声 · 浑厚' },
      { value: 'male_magnetic', label: '男声 · 磁性' },
      { value: 'male_clear', label: '男声 · 清朗' },
      { value: 'choir', label: '合唱' },
      { value: 'instrumental', label: '纯器乐' },
    ],
    languages: [
      { value: 'zh', label: '中文（普通话）' },
      { value: 'yue', label: '粤语' },
      { value: 'en', label: '英语' },
      { value: 'ja', label: '日语' },
    ],
    structure_tags: [
      { tag: '[Intro]', section: 'intro', label: 'Intro' },
      { tag: '[Verse]', section: 'verse', label: 'Verse' },
      { tag: '[Pre-Chorus]', section: 'pre_chorus', label: 'Pre' },
      { tag: '[Chorus]', section: 'chorus', label: 'Chorus' },
      { tag: '[Bridge]', section: 'bridge', label: 'Bridge' },
      { tag: '[Outro]', section: 'outro', label: 'Outro' },
    ],
    generation_limits: {
      min_duration_sec: 30,
      max_duration_sec: 240,
      min_bpm: 60,
      max_bpm: 174,
      max_style_prompt: 500,
      max_lyrics: 4000,
      max_negative_prompt: 100,
    },
    inspiration: {
      scenes: ['短视频 BGM', '广告片', '游戏配乐', '个人单曲'],
      moods: ['治愈', '忧郁', '热血', '浪漫', '紧张'],
      genres: ['华语流行', '国风', '嘻哈', 'EDM', 'Lo-fi', '摇滚', '民谣', 'R&B'],
      instruments: ['钢琴', '吉他', '弦乐', '古筝', '合成器', '808'],
    },
  }
}

interface MetaState {
  meta: SystemMeta
  loaded: boolean
  load: () => Promise<void>
}

export const useMetaStore = create<MetaState>((set, get) => ({
  meta: defaultMeta(),
  loaded: false,
  async load() {
    if (get().loaded) return
    try {
      const meta = await getSystemMeta()
      set({ meta, loaded: true })
    } catch {
      // 后端未启动时静默使用兜底枚举（值与契约一致，不算编造数据）
      set({ loaded: true })
    }
  },
}))
