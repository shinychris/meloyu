import { pitchEn } from '../en/pitch'

/** zh 字典 key 与 en 严格一一对应（编译期校验，漏 key 报 type error）。 */
export const pitchZh: Record<keyof typeof pitchEn, string> = {
  'pitch.view.label': '制作 / 修调 · 旋律修调',
  'pitch.view.headline': '钢琴卷帘音符编辑 · 确定性重渲染',
  'pitch.pick.work': '选择作品…',
  'pitch.empty': '选择一首有已采纳候选的作品（本地引擎版本自带旋律 MIDI）',
  'pitch.empty.notes': '该版本没有旋律音符（外部通道候选无 MIDI）',
  'pitch.snapScale': '吸附音阶',
  'pitch.quantize.off': '不量化',
  'pitch.quantize.8': '量化 1/8',
  'pitch.quantize.16': '量化 1/16',
  'pitch.hint.select': '点击音符选中 · ↑/↓ 移动半音',
  'pitch.selected': '{name} · {s:+0} 半音',
  'pitch.submit': '重渲染（{n} 处修改）',
  'pitch.submitting': '重渲染中…',
  'pitch.submit.hint':
    '同 seed 确定性重渲染：编曲/人声/歌词对齐保持一致，仅音符音高与位置变化（6 积分）',
  'pitch.toast.noEdits': '请先选中音符并上下移动',
  'pitch.toast.quantizeOnly': '仅提交节奏量化',
  'pitch.toast.snapped': '已把 {n} 个音符吸附回音阶',
  'pitch.toast.allInScale': '所有音符都在调内',
  'pitch.toast.done': '修调版本已生成（v{no}）',
  'pitch.toast.failed': '重渲染失败',
  'pitch.footnote':
    '数据源为词谱旋律（候选 MIDI）。你有意保留的离调音（蓝调音等）不会被强制吸附。',
}
