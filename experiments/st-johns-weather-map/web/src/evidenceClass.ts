import type { EvidenceClass, LayerItem, ResolvedEvidenceClass } from './types'

/** The six classes the API declares, in the order the legend lists them:
 *  strongest claim first, display-only and uncalibrated last. The list is the
 *  client's whole vocabulary — a seventh name is `unrecognised`, never
 *  resolved to the nearest neighbour. */
export const EVIDENCE_CLASSES: readonly EvidenceClass[] = [
  'retrieved',
  'reprocessed',
  'derived_here',
  'intermediary_derived',
  'generated_display',
  'uncalibrated_observation',
] as const

/** What a response's `evidence_class` resolves to here. Anything that is not
 *  one of the six — including an absent field, which the contract says is
 *  required with no default — is `unrecognised`. It is never treated as
 *  `retrieved`: the whole point of the field is that the strongest claim is
 *  the one that must be declared rather than assumed. */
export function resolveEvidenceClass(value: unknown): ResolvedEvidenceClass {
  return typeof value === 'string' && (EVIDENCE_CLASSES as readonly string[]).includes(value)
    ? (value as EvidenceClass)
    : 'unrecognised'
}

/** Exactly what the response said, for the reason sentence. Null when it
 *  declared nothing at all — a different failure from declaring nonsense. */
export function declaredEvidenceClass(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value : null
}

export const EVIDENCE_CLASS_LABELS: Record<ResolvedEvidenceClass, string> = {
  retrieved: 'retrieved',
  reprocessed: 'reprocessed',
  derived_here: 'derived here',
  intermediary_derived: 'intermediary derived',
  generated_display: 'generated display',
  uncalibrated_observation: 'uncalibrated observation',
  unrecognised: 'unrecognised evidence class',
}

/** One sentence per class, in the glossary's words (`CONTEXT.md`), so the
 *  legend and every tooltip say the same thing about what a badge means. */
export const EVIDENCE_CLASS_DESCRIPTIONS: Record<ResolvedEvidenceClass, string> = {
  retrieved: 'This deployment fetched the value as the producer issued it.',
  reprocessed: 'An intermediary transformed the producer’s value before delivery; producer and intermediary are named. Never the display primary and never a derivation input.',
  derived_here: 'This deployment computed the value from retrieved inputs by a registered, cited derivation method. Its inputs and method are listed on demand.',
  intermediary_derived: 'An intermediary computed the value from the producer’s retrieved fields by the intermediary’s own method. Never the display primary and never a derivation input.',
  generated_display: 'A display-only interpolation between retrieved frames. Never on a data path.',
  uncalibrated_observation: 'A citizen or personal instrument. Never used for verification.',
  unrecognised: 'The response declared no evidence class, or one this client does not know. Nothing is shown for it: an undeclared class is never read as retrieved.',
}

/** Why a value is not shown. Both forms contain the phrase the spec names,
 *  and they stay apart because "declared nothing" and "declared a name we do
 *  not know" are different failures on the API side. */
export function unrecognisedClassReason(declared: string | null): string {
  return declared === null
    ? 'unrecognised evidence class — the response declared none'
    : `unrecognised evidence class “${declared}”`
}

/** A layer's evidence class as a sentence, for the map's text alternative.
 *  The same claim the drawer badge makes, so a reader without sight of the
 *  drawer never gets a weaker one. Lives here rather than in `MapPanel` so it
 *  can be read without pulling MapLibre in behind it. */
export function describeEvidenceClassSentence(layer: LayerItem): string {
  const evidenceClass = resolveEvidenceClass(layer.evidence_class)
  if (evidenceClass === 'unrecognised') {
    return `Evidence class unavailable: ${unrecognisedClassReason(layer.evidence_class ?? null)}.`
  }
  return `Evidence class ${EVIDENCE_CLASS_LABELS[evidenceClass]}: ${EVIDENCE_CLASS_DESCRIPTIONS[evidenceClass]}`
}

/** The legend rows, all six plus the unrecognised state, so the absence of a
 *  badge never carries meaning: every state a reader can see is named. */
export const EVIDENCE_CLASS_LEGEND: Array<{ evidenceClass: ResolvedEvidenceClass; label: string; description: string }> =
  [...EVIDENCE_CLASSES, 'unrecognised' as const].map((evidenceClass) => ({
    evidenceClass,
    label: EVIDENCE_CLASS_LABELS[evidenceClass],
    description: EVIDENCE_CLASS_DESCRIPTIONS[evidenceClass],
  }))
