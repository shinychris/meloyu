import { create } from 'zustand'
import type { SystemMeta } from '../types/api'
import { getSystemMeta } from '../api/account'

const TONICS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const

function defaultKeys(): SystemMeta['keys'] {
  const list: SystemMeta['keys'] = []
  for (const mode of ['major', 'minor'] as const) {
    for (const tonic of TONICS) {
      // 兜底数据为默认语言 en；后端可达时由 /system/meta 按 Accept-Language 返回本地化 label
      list.push({ tonic, mode, label: `${tonic} ${mode === 'major' ? 'Major' : 'Minor'}` })
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
        label: 'V1 Pro · High quality',
        credit_cost: 12,
        capabilities: { vocals: true, midi: true, stems: 4 },
      },
      {
        value: 'v1_fast',
        label: 'V1 · Fast draft',
        credit_cost: 6,
        capabilities: { vocals: true, midi: true, stems: 4 },
      },
    ],
    keys: defaultKeys(),
    time_signatures: ['4/4', '3/4', '6/8'],
    vocal_types: [
      { value: 'female_air', label: 'Female · breathy' },
      { value: 'female_bright', label: 'Female · bright' },
      { value: 'female_deep', label: 'Female · deep' },
      { value: 'male_magnetic', label: 'Male · magnetic' },
      { value: 'male_clear', label: 'Male · clear' },
      { value: 'choir', label: 'Choir' },
      { value: 'instrumental', label: 'Instrumental' },
    ],
    languages: [
      { value: 'zh', label: 'Chinese (Mandarin)' },
      { value: 'yue', label: 'Cantonese' },
      { value: 'en', label: 'English' },
      { value: 'ja', label: 'Japanese' },
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
      scenes: ['Short-video BGM', 'Ad film', 'Game score', 'Solo single'],
      moods: ['Healing', 'Melancholy', 'Energetic', 'Romantic', 'Tense'],
      genres: ['Mandopop', 'Chinese traditional', 'Hip-hop', 'EDM', 'Lo-fi', 'Rock', 'Folk', 'R&B'],
      instruments: ['Piano', 'Guitar', 'Strings', 'Guzheng', 'Synth', '808'],
    },
  }
}

interface MetaState {
  meta: SystemMeta
  loaded: boolean
  load: () => Promise<void>
  /** 语言切换后重拉：后端按 Accept-Language 返回本地化 label/灵感词条 */
  reloadForLocale: () => Promise<void>
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
  async reloadForLocale() {
    try {
      const meta = await getSystemMeta()
      set({ meta })
    } catch {
      /* 保留现有兜底 */
    }
  },
}))
