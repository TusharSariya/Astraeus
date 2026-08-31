import type { FieldDataMode } from './types'

/** Per-field honesty label. Small and quiet by design: real values must
 *  always read as the primary content, this only qualifies them. */
export function ModeChip({ mode }: { mode: FieldDataMode | undefined }) {
  if (!mode || mode === 'live') return null
  const copy = mode === 'fixture' ? 'fixture value' : mode === 'mixed' ? 'mixed provenance' : 'not declared live'
  return <em className={`mode-chip ${mode}`}>{copy}</em>
}
