import { useNavigate } from 'react-router-dom'

type Kind = 'arrange' | 'edit' | 'pitch'

const META: Record<Kind, { label: string; title: string; desc: string; features: string[] }> = {
  arrange: {
    label: 'Arrange / 编曲',
    title: '多轨时间线编曲',
    desc: '六轨时间线（主唱/鼓/贝斯/钢琴/弦乐/FX）、clip 拖拽与切割、AI 编曲建议（结构/频段/对比/衔接）——将在 V2 版本上线。MVP 阶段请在作品详情页导出分轨与 MIDI，到你的 DAW 中继续编排。',
    features: ['多轨 clip 编辑（移动/切割/画笔/擦除）', 'AI 编曲建议 · 一键应用', 'Mute / Solo / 声像', '版本冻结与回退'],
  },
  edit: {
    label: 'Edit / 音频剪辑',
    title: '非破坏性音频剪辑',
    desc: '波形选区编辑、淡入淡出、增益/标准化、AI 降噪与去房混、爆音一键修复——将在 V2 版本上线。当前导出的 48kHz/24bit WAV 与 4 Stems 可直接导入专业 DAW 处理。',
    features: ['选区操作 + 撤销栈', 'AI 降噪 / 去房混 / 呼吸控制', 'Clip 效果链（非破坏性）', '爆音与空白检测'],
  },
  pitch: {
    label: 'Pitch / 修调',
    title: '旋律修调工坊',
    desc: '钢琴卷帘式音符编辑、音高吸附音阶、节奏量化、颤音/滑音保留控制——将在 V2 版本上线。MVP 的合成人声音高由 MusiCoT 管线直接对齐音阶，无需修调。',
    features: ['音符拖拽移调（吸附半音）', '修正强度 / 颤音保留 / 共振峰', '节奏量化 1/8 · 1/16', '跑调检测与一键修复'],
  },
}

/** 编曲 / 音频剪辑 / 修调 —— V2 占位页（保留侧边栏入口，无任何后端接口） */
export default function ComingSoonView({ kind }: { kind: Kind }) {
  const meta = META[kind]
  const navigate = useNavigate()

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4 flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="label">{meta.label}</div>
          <h1 className="text-[28px] font-extrabold tracking-tight mt-1">{meta.title}</h1>
        </div>
        <span
          className="text-[11px] px-2 py-1 font-bold"
          style={{ background: 'var(--acc-dim)', color: 'var(--acc)' }}
        >
          V2 开发中 · 即将上线
        </span>
      </header>

      <div className="rule-t flex-1 px-8 py-8 overflow-y-auto">
        <div className="border border-dashed py-14 text-center" style={{ borderColor: 'var(--line)' }}>
          <svg className="mx-auto" width="44" height="44" viewBox="0 0 44 44" fill="none">
            <rect x="4" y="18" width="4" height="12" fill="#2c2c2c" />
            <rect x="12" y="11" width="4" height="26" fill="#2c2c2c" />
            <rect x="20" y="5" width="4" height="34" fill="#00ff2c" />
            <rect x="28" y="13" width="4" height="22" fill="#2c2c2c" />
            <rect x="36" y="9" width="4" height="28" fill="#2c2c2c" />
          </svg>
          <div className="text-[14px] mt-4 font-semibold" style={{ color: 'var(--muted)' }}>
            「{meta.title}」即将上线
          </div>
          <div className="text-[11px] mt-2 leading-relaxed max-w-[560px] mx-auto" style={{ color: 'var(--dim)' }}>
            {meta.desc}
          </div>
          <div className="flex gap-1.5 mt-5 justify-center flex-wrap px-4">
            {meta.features.map((f) => (
              <span key={f} className="chip acc-on" style={{ cursor: 'default' }}>{f}</span>
            ))}
          </div>
          <div className="flex gap-2 mt-6 justify-center">
            <button className="btn btn-acc !py-2 !px-4 text-[12px] font-bold" onClick={() => navigate('/studio')}>
              返回创作工作台
            </button>
            <button className="btn btn-ghost !py-2 !px-4 text-[12px]" onClick={() => navigate('/library')}>
              去作品库导出
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}
