/** pitch 命名空间：旋律修调（PitchView，v0.11.0）。 */
export const pitchEn = {
  'pitch.view.label': 'Production / Pitch · Melody tuning',
  'pitch.view.headline': 'Piano-roll note editing · deterministic re-render',
  'pitch.pick.work': 'Select a work…',
  'pitch.empty': 'Pick a work with an adopted candidate (local-engine versions carry melody MIDI)',
  'pitch.empty.notes': 'This version has no melody notes (external-channel candidates have no MIDI)',
  'pitch.snapScale': 'Snap to scale',
  'pitch.quantize.off': 'No quantize',
  'pitch.quantize.8': 'Quantize 1/8',
  'pitch.quantize.16': 'Quantize 1/16',
  'pitch.hint.select': 'Click a note to select · ↑/↓ semitone',
  'pitch.selected': '{name} · {s:+0} semitones',
  'pitch.submit': 'Re-render ({n} edits)',
  'pitch.submitting': 'Re-rendering…',
  'pitch.submit.hint':
    'Same-seed deterministic re-render: arrangement/vocals/lyrics stay identical, only note pitch/position change (6 credits)',
  'pitch.toast.noEdits': 'Select notes and move them up/down first',
  'pitch.toast.quantizeOnly': 'Quantize-only submission',
  'pitch.toast.snapped': 'Snapped {n} notes to scale',
  'pitch.toast.allInScale': 'All notes already in scale',
  'pitch.toast.done': 'Tuned version saved ({no})',
  'pitch.toast.donePlain': 'Tuned version saved',
  'pitch.toast.failed': 'Re-render failed',
  'pitch.footnote':
    'Source: leadsheet melody (candidate MIDI). Off-scale notes you keep intentionally (blue notes) are preserved as-is.',
} as const
