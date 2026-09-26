import { layoutEn } from '../en/layout'

/** zh 字典 key 与 en 严格一一对应（编译期校验，漏 key 报 type error） */
export const layoutZh: Record<keyof typeof layoutEn, string> = {
  // Onboarding 新手引导
  'layout.ob.progress': '第 {current} / {total} 步',
  'layout.ob.skip': '跳过',
  'layout.ob.finished': '引导结束 · 随时可在左下角重新打开',
  'layout.ob.askTitle': '是否开启新手引导？',
  'layout.ob.askDesc': '欢迎！4 步快速上手：灵感 → 歌词 → 生成 → 编曲。跳过也没关系，随时可在侧栏左下角重新打开。',
  'layout.ob.askStart': '开启引导',
  'layout.ob.askSkip': '暂不',
  'layout.ob.step1.title': '描述你的灵感',
  'layout.ob.step1.desc': '点选场景、情绪、风格与主奏乐器，系统自动组装专业提示词；也可以直接改写下方描述。',
  'layout.ob.step2.title': '歌词与结构',
  'layout.ob.step2.desc': '粘贴歌词，用 [Verse]/[Chorus] 等标签告诉 AI 歌曲结构；没有歌词可在「歌词助手」里让 AI 起草。',
  'layout.ob.step3.title': '生成与挑选',
  'layout.ob.step3.desc': '每次产出 2 个候选并给出 AI 质量分；不满意可整首重生成，或只对某段落局部重生成（V1.1）。',
  'layout.ob.step4.title': '进入专业制作',
  'layout.ob.step4.desc': '满意的候选可「送往编曲」：多轨时间线编排、音频剪辑、修调将在 V2 上线；现在即可在作品库导出可商用的成品与授权证书。',
  // TransportBar 播放条
  'layout.player.prev': '上一首',
  'layout.player.next': '下一首',
  'layout.player.play': '播放',
  'layout.player.pause': '暂停',
  'layout.player.target': '目标',
  'layout.player.lufsTitle': '导出目标规格（流媒体预设），非实时测量值',
  'layout.player.export': '导出',
  'layout.player.exportTitle': '在作品详情页导出 WAV / MP3 / MIDI / Stems 与证书',
  // player store toast
  'layout.player.autoplayBlocked': '浏览器阻止了自动播放，请再点一次播放',
  'layout.player.nothingToPlay': '还没有可播放的音频，先在作品库或工作台试听',
  'layout.player.noNext': '没有下一首',
  'layout.player.noPrev': '没有上一首',
  // Pagination 分页
  'layout.pagination.status': '{page} / {total} 页',
  'layout.pagination.prev': '上一页',
  'layout.pagination.next': '下一页',
  // SearchInput 搜索框
  'layout.search.placeholder': '搜索…',
  'layout.search.clear': '清空搜索',
}
