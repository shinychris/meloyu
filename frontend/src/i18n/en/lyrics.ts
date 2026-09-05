/** lyrics 命名空间：歌词助手页（LyricsView + AnalysisPanel） */
export const lyricsEn = {
  // 视图头部
  'lyrics.header.label': 'Lyrics / Assistant',
  'lyrics.header.headline': 'Write lyrics that lock to the melody',
  'lyrics.engine.badge': 'Engine: {engine} ⇄',
  'lyrics.engine.title':
    'Switch the AI lyrics engine in Model Center (local rules / local open-source model / external API)',
  // 生成参数
  'lyrics.theme.label': 'Theme / one line (required to generate)',
  'lyrics.theme.placeholder': 'e.g. waiting at a convenience store on a rainy night',
  'lyrics.mood.label': 'Mood (optional, e.g. melancholic / fired-up)',
  'lyrics.mood.placeholder': 'Matches the imagery library',
  // 操作按钮
  'lyrics.action.generate': 'Generate with AI',
  'lyrics.action.generating': 'Generating…',
  'lyrics.action.generatingLLM': 'AI generating (up to ~3 min)…',
  'lyrics.action.generateTitle': 'LLM generation may take 10s–3min depending on the model',
  'lyrics.action.polish': 'Polish selected section',
  'lyrics.action.polishing': 'Polishing…',
  'lyrics.action.rhyme': 'Rhyme / stress check',
  'lyrics.action.checking': 'Checking…',
  'lyrics.action.tags': 'Complete structure tags',
  'lyrics.action.apply': 'Apply to Studio →',
  // 备选版本
  'lyrics.alternatives': 'Alternative drafts',
  'lyrics.alternative': 'Alt {n}',
  'lyrics.toast.altLoaded': 'Loaded alternative {n}',
  // 提示
  'lyrics.toast.themeRequired': 'Enter a theme or one-line idea first (1–100 characters)',
  'lyrics.toast.empty': 'The lyrics are empty',
  'lyrics.toast.fallback': 'Engine unavailable, fell back to local rules: {reason}',
  'lyrics.toast.generated': 'AI lyrics draft generated ({engine}) — ready to polish',
  'lyrics.toast.polishedSection': 'Polished {section} ({n} edits)',
  'lyrics.toast.polishedAll': 'Polished the full lyric ({n} edits)',
  'lyrics.toast.rhymeOff': 'Check done: {n} lines off-rhyme, main rhyme {group}',
  'lyrics.toast.rhymeAll': 'Check done: fully rhymed (main rhyme {group})',
  'lyrics.toast.tagsInferred': 'No tags in the original lyric — structure completed from template',
  'lyrics.toast.tagsNormalized': 'Structure tags recognized and normalized',
  'lyrics.toast.applied': 'Applied to the lyrics panel in Studio',
  'lyrics.toast.backStudio': 'Back in the Studio',
  // 操作日志（VersionTree 展示）
  'lyrics.log.generated': 'Lyrics assistant: AI draft generated',
  // 右侧分析面板
  'lyrics.panel.structure': 'Structure advice',
  'lyrics.panel.structureDefault':
    'Repeat the chorus hook 2–3 times; drop the bridge a semitone for contrast, then lift into the final chorus.',
  'lyrics.panel.sectionCount': '{section}: {n} lines',
  'lyrics.panel.tagDetect': 'Tags detected: {tags}',
  'lyrics.panel.none': 'None',
  'lyrics.panel.polishLog': 'Polish log',
  'lyrics.panel.stress': 'Stress alignment',
  'lyrics.panel.stressOk': 'Stresses land on the beat',
  'lyrics.panel.stressPending': 'Run “Rhyme / stress check” to see results',
  'lyrics.panel.rhyme': 'Rhyme ends',
  'lyrics.panel.rhymeMain': ' · main rhyme {group}',
  'lyrics.panel.backStudio': 'Back to Studio →',
  'lyrics.defaultLyrics':
    '[Verse]\nRain stops at the window sill past midnight\nNeon stretches my shadow far too pale\nThe corner store light is still on\nLike a line left unsaid\n\n[Pre-Chorus]\nI count the rhythm dripping from the eaves\nBeat by beat, all of it waiting\n\n[Chorus]\nWe spoke of the future far too lightly\nLike wind through an empty street\nIf a promise is only an echo\nAt least tonight there is still the rain',
} as const
