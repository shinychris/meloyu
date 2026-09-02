/** work 命名空间：作品详情（WorkDetailView + ExportPanel） */
export const workEn = {
  // 视图头部
  'work.header.label': 'Work / Details · {code}',
  'work.notFound': 'Work not found or not accessible',
  'work.backLibrary': 'Back to Library',
  'work.backLibraryArrow': '← Back to Library',
  // 标题 / 标签编辑
  'work.edit.titlePlaceholder': 'Title (1–50 characters)',
  'work.edit.tagsPlaceholder': 'Tags, comma-separated (max 8, each 1–12 characters)',
  'work.edit.saving': 'Saving…',
  'work.edit.titleButton': 'Edit title and tags',
  'work.meta.versions': 'Versions ×{n}',
  // 版本树
  'work.tree': 'Version tree',
  'work.tree.current': 'Current',
  'work.tree.nodeTitle': '{source} · candidates ×{n}',
  // 候选列表
  'work.candidates': 'Candidates',
  'work.candidates.hint': 'Low-bitrate preview · export unlocks after adopting',
  'work.candidates.empty': 'No candidates for this version',
  'work.candidate.name': 'Candidate {label}',
  'work.candidate.untitledWork': 'Work',
  'work.candidate.external': 'External model',
  'work.candidate.quality': 'AI quality {n}',
  'work.candidate.adopted': 'Finalized',
  'work.candidate.adopt': 'Adopt as final',
  'work.candidate.segTitle': '{section} · {n} bars',
  'work.action.preview': 'Preview',
  // 提示
  'work.toast.adopted': 'Candidate {label} adopted as the final version',
  'work.toast.noPreview': 'This candidate has no preview audio',
  'work.toast.titleLength': 'Title must be 1–50 characters',
  'work.toast.tagsMax': 'Up to 8 tags',
  'work.toast.tagLength': 'Each tag must be 1–12 characters',
  'work.toast.saved': 'Work details updated',
  // 导出面板
  'work.export.title': 'Export & certificate',
  'work.export.run': 'Export {format}',
  'work.export.processing': 'Processing {n}%…',
  'work.export.note.wav': '48kHz / 24-bit master',
  'work.export.note.mp3': '320k CBR',
  'work.export.note.midi': 'melody/chords/bass/drums ×4',
  'work.export.note.stems': 'vocals/drums/bass/other ZIP',
  'work.export.certificate': 'Download license certificate (JSON)',
  'work.export.generating': 'Generating…',
  'work.export.footnote':
    'Exports cost no credits; adopt a candidate first. The certificate carries the human-creation provenance and a SHA-256 content fingerprint.',
  'work.export.toast.done': 'Export done: {format} download started ({n} files)',
  'work.export.toast.noFiles': 'Export finished, but no file list was returned',
  'work.export.failed': 'Export failed',
  'work.export.toast.pollBroken': 'Export task polling interrupted',
  'work.export.toast.certStarted': 'License certificate JSON download started',
} as const
