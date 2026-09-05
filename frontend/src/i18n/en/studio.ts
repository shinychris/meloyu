/**
 * studio 命名空间：创作工作台（StudioView / components/studio / stores/studio）。
 * 术语对齐 DAW / Suno 语境：风格描述 → style prompt、候选 → candidate、
 * 采用定稿 → adopt、变体 → variant、段落重生成 → section re-gen。
 */
export const studioEn = {
  // ===== 视图头部 / 模式 =====
  'studio.view.label': 'Studio / Workstation',
  'studio.view.headline': 'From one line to a release-ready song',
  'studio.view.vocalOptimized': 'Chinese-vocal optimized',
  'studio.view.songEngine': 'Song engine: {name} ⇄',
  'studio.view.songEngineTitle':
    'Switch the song engine in Model Center (local synthesis / external song API); the lyrics engine is configured there as well',
  'studio.mode': 'Mode',
  'studio.mode.simple': 'One-liner',
  'studio.mode.custom': 'Custom',
  'studio.mode.ref': 'Reference audio',
  'studio.mode.hum': 'Hum-to-song',
  'studio.hum.title': 'Hum to song',
  'studio.hum.desc':
    "Hum a melody (10-30s, steady 'ahh'/'doo'); we extract the pitch contour and map it onto the AI-generated vocal - intervals preserved, key-fitted.",
  'studio.hum.record': 'Record humming',
  'studio.hum.stop': 'Stop',
  'studio.hum.analyzing': 'Analyzing…',
  'studio.hum.micDenied': 'Microphone access denied',
  'studio.hum.result': '{n} notes · {sec}s · tempo ≈{bpm} BPM · confidence {conf}%',
  'studio.hum.apply': 'Use this melody',
  'studio.hum.applied': 'Hummed melody applied ({n} notes) - generation now uses it',
  'studio.modeHint.simple': 'One-liner mode: describe the whole song in natural language',
  'studio.modeHint.custom': 'Custom mode: style prompt + structure-tagged lyrics + parameters',
  'studio.modeHint.ref': 'Reference audio: upload a track (≤8 min) — tempo/key/energy features as a reference (not sampling)',

  // ===== 左列输入 =====
  'studio.simple.label': 'One-line description',
  'studio.simple.placeholder':
    'e.g. A Mandopop ballad set in a rainy-night convenience store, piano backing, female vocals',
  'studio.simple.hint':
    'Lyrics and structure are generated from your description — or switch to the Lyrics Assistant to write first.',
  'studio.style.label': 'Style prompt',
  'studio.lyrics.label': 'Lyrics',
  'studio.lyrics.tagCount': '({n} structure tags detected)',
  'studio.lyrics.openAssistant': 'Refine in Lyrics Assistant →',
  'studio.toast.switchedToLyrics': 'Switched to the Lyrics Assistant',
  'studio.param.label': 'Parameters & model',
  'studio.generate.generating': 'Generating…',
  'studio.generate.button': 'Generate 2 candidates · {n} credits',
  'studio.generate.complianceNote':
    'Paid-plan outputs include a commercial license; every step is traceable — download your license certificate in Rights & Compliance.',

  // ===== 结果列 / 失败 / 空状态 =====
  'studio.candidates.title': 'Candidates',
  'studio.candidates.previewNote': 'Previews are low-bitrate · exports at 48 kHz / 24-bit',
  'studio.failure.title': 'Generation failed',
  'studio.failure.retrySimplified': 'Retry (simplified prompt)',
  'studio.failure.retryOriginal': 'Retry with original params',
  'studio.failure.note':
    'Credits for failed runs are refunded automatically; a simplified retry halves the style-prompt keywords.',
  'studio.untitled': 'Untitled work',
  'studio.empty.title': 'First version in three steps',
  'studio.empty.step1': '① Pick a scene / mood / genre under “Inspiration” on the left',
  'studio.empty.step2': '② Paste lyrics or tap structure tags → ③ hit “Generate 2 candidates”',
  'studio.empty.random': 'Start with a random inspiration',
  'studio.toast.randomInspired': 'Random inspiration applied',

  // ===== 四步引导条 =====
  'studio.step.1': 'Describe ideas',
  'studio.step.2': 'Lyrics & structure',
  'studio.step.3': 'Parameters & model',
  'studio.step.4': 'Generate & refine',

  // ===== 灵感指引 =====
  'studio.inspire.title': 'Inspiration',
  'studio.inspire.random': 'Random set ↻',
  'studio.inspire.hint': 'Tap a combination — it fills the style prompt automatically',
  'studio.inspire.scene': 'Scene',
  'studio.inspire.mood': 'Mood',
  'studio.inspire.genre': 'Genre',
  'studio.inspire.inst': 'Lead instrument',
  'studio.toast.inspireRandom': 'Random inspiration set generated',

  // ===== 参数面板 =====
  'studio.param.language': 'Language',
  'studio.param.vocal': 'Vocals',
  'studio.param.key': 'Key',
  'studio.param.timeSignature': 'Time signature',
  'studio.param.duration': 'Duration',
  'studio.param.model': 'Model',
  'studio.param.durationFull': 'Full song ≈ 3:30',
  'studio.param.durationShort': 'Short clip ≈ 1:00',
  'studio.param.durationLoop': 'Loop ≈ 0:30',
  'studio.param.durationCustom': 'Custom {n}s',
  'studio.param.density': 'Instrument density',
  'studio.param.negative': 'Excluded elements (negative prompt)',
  'studio.param.negativePlaceholder': 'e.g. no drum machines, no electronic vocals',

  // ===== 生成进度 =====
  'studio.progress.queued': 'Queued…',
  'studio.progress.cancelTitle': 'Canceling refunds all credits',
  'studio.progress.pipeline': 'MusiCoT structure planning → arrangement → vocal synthesis → mastering',

  // ===== 候选卡 =====
  'studio.card.title': '{work} · Candidate {label}',
  'studio.card.playTitle': 'Preview',
  'studio.card.noPreview': 'No preview audio for this candidate yet',
  'studio.card.external': 'External model',
  'studio.card.quality': 'AI quality {n}',
  'studio.card.externalTitle': 'External-model candidates do not produce an AI quality score',
  'studio.card.finalized': 'Finalized',
  'studio.card.adopt': 'Adopt & finalize',
  'studio.card.busyTitle': 'Generation in progress, please wait',
  'studio.card.extend': 'Extend',
  'studio.card.extendTitle': 'Continue 15–60s from the end into a new child version',
  'studio.card.variant': 'Variant',
  'studio.card.variantTitle': 'Same structure, new style — creates a new child version',
  'studio.card.regen': 'Regen section',
  'studio.card.regenTitle': 'Pick a section to regenerate; the rest stays unchanged',
  'studio.card.arrange': 'Send to arrange →',
  'studio.card.export': 'Export',
  'studio.card.exportTitle': 'Open the work to export WAV / MP3 / MIDI / Stems and certificates',
  'studio.card.bars': '{section} · {n} bars',

  // ===== 派生操作面板（延长 / 变体 / 段落重生成） =====
  'studio.derive.extend.title': 'Extend',
  'studio.derive.variant.title': 'Variant',
  'studio.derive.regen.title': 'Section re-gen',
  'studio.derive.extend.hint':
    'Continues from the end into a new child version (costs credits, auto-refunded on failure)',
  'studio.derive.variant.hint': 'Keeps structure and lyrics, swaps only the style — creates a new child version',
  'studio.derive.variant.placeholder': 'New style prompt (leave blank = auto restyle)',
  'studio.derive.variant.aria': 'New style prompt',
  'studio.derive.regen.hint':
    'Only the selected section is regenerated; the rest stays unchanged. Repeated sections are marked #1, #2, …',
  'studio.derive.regen.empty': 'No structure info for this candidate — cannot locate sections',
  'studio.derive.regen.pickFirst': 'Select a section first',
  'studio.derive.submitting': 'Submitting…',
  'studio.derive.extend.submit': 'Extend {n}s',
  'studio.derive.variant.submit': 'Create variant',
  'studio.derive.regen.submit': 'Regen this section',
  'studio.derive.seg': '{section} · {bars} bars · {range}',

  // ===== 版本树侧栏 =====
  'studio.tree.title': 'Version tree',
  'studio.tree.new': '+ New work',
  'studio.tree.newTitle': 'Clears the current context; the next generation starts a new work',
  'studio.tree.empty': 'Nothing yet · the version tree appears after your first generation',
  'studio.tree.node': '{no} · {source} · {n} candidates',
  'studio.tree.recentOps': 'Recent activity',

  // ===== toast / 校验 / 失败提示 =====
  'studio.toast.adopted': 'Candidate {label} adopted as the current version',
  'studio.toast.sentArrange': 'Sent to arrange: {title} (continue multitrack mixing in the Arrange view)',
  'studio.toast.detailPending': 'Work details still generating, please wait',
  'studio.toast.generated': 'Generated {n} candidates',
  'studio.toast.generatedEmpty': 'Generation complete',
  'studio.toast.structureInferred': 'Lyrics had no structure tags — structure was added automatically',
  'studio.toast.cancelRequested': 'Cancel requested, stopping…',
  'studio.warn.simpleEmpty': 'Describe the song you want in one line first',
  'studio.warn.styleEmpty': 'Style prompt cannot be empty',
  'studio.fail.default': 'Generation failed',
  'studio.fail.canceled': 'Generation canceled, credits refunded',
  'studio.fail.pollLost': 'Lost track of task status, please try again later',

  // ===== 操作日志（opLog） =====

// ===== Reference audio (FR-4, v0.8.1) =====
'studio.ref.title': 'Reference audio',
'studio.ref.pick': 'Choose an audio file (mp3 / wav / m4a)',
'studio.ref.analyzing': 'Uploading & analyzing…',
'studio.ref.ack': 'I confirm I hold the rights to this audio; reference extraction only (tempo/key/energy) — no waveform sampling.',
'studio.ref.hint': '≤8 minutes / ≤50MB. The analysis (BPM/key/energy) is applied to generation params and attached at submit.',
'studio.ref.major': 'major',
'studio.ref.minor': 'minor',
'studio.ref.applyParams': 'Apply to params',
'studio.ref.attachedNote': 'Attached to this generation (feature-level); analysis values override BPM/key/density on submit.',
'studio.ref.remove': 'Remove reference',
'studio.ref.toast.tooLarge': 'File exceeds the 50MB limit',
'studio.ref.toast.ackRequired': 'Please confirm the rights checkbox first',
'studio.ref.toast.analyzeFailed': 'Analysis incomplete: audio may be undecodable',
'studio.ref.toast.ready': 'Reference ready: {name}',
'studio.ref.log.applied': 'Reference features applied: {bpm} BPM · {key}',

// ===== My voice (FR-5, v0.8.2) =====
'studio.voice.title': 'My voice (voice cloning)',
'studio.voice.hint': 'Two-random-phrase liveness check (your own voice only): read two different server-issued phrases; after the same-speaker check your voice becomes usable in generation.',
'studio.voice.manage': 'Enroll / manage my voice',
'studio.voice.pickFirst': 'Select or enroll a verified voice profile first',
'studio.voice.enroll': 'Enroll',
'studio.voice.namePlaceholder': 'Profile name (e.g. "My voice")',
'studio.voice.step1': 'Step 1 · Read this sentence aloud:',
'studio.voice.step2': 'Step 2 · Read another one (freshly issued, replay-safe):',
'studio.voice.record': 'Start recording',
'studio.voice.stop': 'Stop when done',
'studio.voice.recording': 'Recording… speak clearly in a quiet place',
'studio.voice.delete': 'Delete this voice profile',
'studio.voice.compliance': 'Own voice only (liveness + consent log); timbre is parameter-level adaptation (range/formants/brightness, not sample concatenation); cloned-track exports carry the AIGC tag. The consistency check is a statistical heuristic, not a neural speaker-verification model.',
'studio.voice.toast.nameRequired': 'Enter a profile name first',
'studio.voice.toast.micDenied': 'Microphone access denied',
'studio.voice.toast.phrase2Ready': 'Sample 1 submitted; now read phrase 2',
'studio.voice.toast.verified': 'Voice verified — pick "My voice" in the vocal dropdown',
'studio.voice.toast.verifyFailed': 'Same-speaker check failed (attempt {n}, similarity {score}%); re-read with the same person',
'studio.voice.toast.selected': 'Voice selected: {name}',
'studio.voice.log.verified': 'Voice profile "{name}" passed liveness verification',
  'studio.log.templateLoaded': 'Loaded template “Mandopop ballad”',
  'studio.log.inspire': 'Inspiration: {detail}',
  'studio.log.preview': 'Previewed: {title}',
  'studio.log.adopted': 'Adopted candidate {label} (final)',
  'studio.log.sentArrange': 'Sent to arrange: {title}',
  'studio.log.generated': 'Generated {n} candidates (task completed)',
  'studio.log.generatedEmpty': 'Generation complete (task completed)',
  'studio.log.submit': 'Generation submitted ({n} credits)',
  'studio.log.submitSimplified': 'Generation submitted ({n} credits) · simplified retry',
  'studio.log.deriveStart': '{op} ({n} credits) → {code} generating a new child version',
  'studio.log.extendOp': 'Extend {n}s',
  'studio.log.variantOp': 'Create variant',
  'studio.log.regenOp': 'Section re-gen {section}',
  'studio.log.deriveOp': '{op} · Candidate {label}',

  // ===== 新会话默认示例内容（stylePrompt / lyrics） =====
  'studio.default.stylePrompt':
    'Mandopop ballad, piano-led with string pads, rainy-night atmosphere, breathy female vocals, chorus lifts',
  'studio.default.lyrics':
    '[Verse]\nRain stops on the windowsill at 3 a.m.\nNeon stretches my shadow pale\n[Chorus]\nWe said the future far too lightly\nLike wind through an empty street',

  // ===== My taste (V2-b, v0.9.1) =====
  'studio.taste.apply': 'Prefill by my taste',
  'studio.taste.applied': 'Params prefilled from your taste (stats over {n} works; freely editable)',
  'studio.taste.empty': 'Library is too small to build a taste profile',

} as const
