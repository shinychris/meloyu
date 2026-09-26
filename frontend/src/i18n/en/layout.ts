/**
 * layout 命名空间：新手引导（Onboarding）、播放条（TransportBar）与
 * player store toast、公共组件（分页/搜索框）文案。
 */
export const layoutEn = {
  // Onboarding 新手引导
  'layout.ob.progress': 'Step {current} / {total}',
  'layout.ob.skip': 'Skip',
  'layout.ob.finished': 'Tour finished · reopen it anytime at the bottom left',
  'layout.ob.askTitle': 'Take the 4-step tour?',
  'layout.ob.askDesc':
    'Welcome! A quick walkthrough covers inspiration → lyrics → generation → arranging. Skip it and you can reopen the tour anytime from the bottom left of the sidebar.',
  'layout.ob.askStart': 'Start tour',
  'layout.ob.askSkip': 'Not now',
  'layout.ob.step1.title': 'Describe your inspiration',
  'layout.ob.step1.desc':
    'Pick a scene, mood, style and lead instrument — the system assembles a professional prompt automatically. You can also rewrite the description below yourself.',
  'layout.ob.step2.title': 'Lyrics & structure',
  'layout.ob.step2.desc':
    'Paste your lyrics and mark the song structure with tags like [Verse]/[Chorus]. No lyrics yet? The Lyrics Assistant can draft them for you.',
  'layout.ob.step3.title': 'Generate & pick',
  'layout.ob.step3.desc':
    'Each run produces 2 candidates with AI quality scores. Not happy? Regenerate the whole song, or re-run just one section (V1.1).',
  'layout.ob.step4.title': 'Go professional',
  'layout.ob.step4.desc':
    'Send a candidate you like to "Arrange": multitrack timeline arrangement, audio editing and pitch correction land in V2 — meanwhile you can already export release-ready masters and license certificates from the Library.',
  // TransportBar 播放条
  'layout.player.prev': 'Previous track',
  'layout.player.next': 'Next track',
  'layout.player.play': 'Play',
  'layout.player.pause': 'Pause',
  'layout.player.target': 'Target',
  'layout.player.lufsTitle': 'Target mastering spec (streaming preset), not a live measurement',
  'layout.player.export': 'Export',
  'layout.player.exportTitle': 'Export WAV / MP3 / MIDI / Stems and certificates from the work detail page',
  // player store toast
  'layout.player.autoplayBlocked': 'Autoplay was blocked by the browser — press play again',
  'layout.player.nothingToPlay': 'Nothing to play yet — preview a track in the Library or Studio first',
  'layout.player.noNext': 'No next track',
  'layout.player.noPrev': 'No previous track',
  // Pagination 分页
  'layout.pagination.status': 'Page {page} of {total}',
  'layout.pagination.prev': 'Previous',
  'layout.pagination.next': 'Next',
  // SearchInput 搜索框
  'layout.search.placeholder': 'Search…',
  'layout.search.clear': 'Clear search',
} as const
