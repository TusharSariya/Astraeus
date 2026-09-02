import { EVIDENCE_CLASS_DESCRIPTIONS, EVIDENCE_CLASS_LABELS, EVIDENCE_CLASS_LEGEND, unrecognisedClassReason } from './evidenceClass'
import type { FieldAttribution, ResolvedEvidenceClass } from './types'

/** The class badge every value and every layer carries.
 *
 *  Rendered for `retrieved` as loudly as for anything else, deliberately: the
 *  spec says the absence of a badge must never carry meaning, so there is no
 *  "quiet default" class that renders nothing. The colour comes from the class
 *  name in CSS (`evidence-class-<class>`), which is the same rule the map, the
 *  readings and the stories use, so one class is one colour everywhere. */
export function EvidenceClassBadge({ evidenceClass, declaredClass, title }: {
  evidenceClass: ResolvedEvidenceClass
  declaredClass?: string | null
  title?: string
}) {
  const label = EVIDENCE_CLASS_LABELS[evidenceClass]
  return (
    <em
      className={`evidence-class evidence-class-${evidenceClass}`}
      data-evidence-class={evidenceClass}
      title={title ?? (evidenceClass === 'unrecognised' ? unrecognisedClassReason(declaredClass ?? null) : EVIDENCE_CLASS_DESCRIPTIONS[evidenceClass])}
    >
      {label}
    </em>
  )
}

/** The badge for a field, from its attribution. Nothing is rendered without an
 *  attribution: there is then no value on screen to qualify. */
export function FieldEvidenceClass({ attribution }: { attribution: FieldAttribution | undefined }) {
  if (!attribution) return null
  return <EvidenceClassBadge evidenceClass={attribution.evidenceClass} declaredClass={attribution.declaredClass} />
}

/** All six classes plus the unrecognised state, so a reader can decode any
 *  badge on screen without leaving it. */
export function EvidenceClassLegend() {
  return (
    <details className="evidence-class-legend">
      <summary>Evidence class legend</summary>
      <p>How each value came to exist. Every value and layer carries one of these badges; a badge is never omitted, so its absence would be a fault rather than a claim.</p>
      <dl>
        {EVIDENCE_CLASS_LEGEND.map(({ evidenceClass, description }) => (
          <div key={evidenceClass} className="evidence-class-legend-row">
            <dt><EvidenceClassBadge evidenceClass={evidenceClass} title={description} /></dt>
            <dd>{description}</dd>
          </div>
        ))}
      </dl>
    </details>
  )
}

function inputLine(input: { sourceId: string | null; product: string | null; validTime: string | null; quality: string | null }): string {
  return [
    input.sourceId ?? input.product ?? 'source not named',
    input.validTime ?? 'valid time not named',
    input.quality ? `quality ${input.quality}` : 'quality not named',
  ].join(' · ')
}

/** A `derived_here` value's inputs and method, on demand.
 *
 *  Closed by default: it is disclosure, not the reading. An input the response
 *  did not fully describe prints what is missing rather than a blank cell, and
 *  a derived value that listed no inputs at all says so — that is a contract
 *  failure on the API side and must be visible, not silently empty. */
export function DerivedEvidenceDetails({ label, attribution }: { label: string; attribution: FieldAttribution | undefined }) {
  if (!attribution || attribution.evidenceClass !== 'derived_here') return null
  const method = attribution.derivationMethod
  const inputs = attribution.derivationInputs
  return (
    <details className="derived-detail">
      <summary>{label}: inputs and method</summary>
      <p className="derived-method">
        Method: {method ? method.name : 'the response named no derivation method'}
        {method?.version ? ` · version ${method.version}` : ' · version not named'}
        {method?.citation ? ` · ${method.citation}` : ' · citation not named'}
      </p>
      <p className="derived-quality">
        Quality: {attribution.qualityStatus ?? 'not named'}
        {attribution.qualityFlags.length > 0 ? ` · flags ${attribution.qualityFlags.join(', ')}` : ' · no flags'}
      </p>
      {inputs.length === 0
        ? <p className="derived-inputs-missing">The response listed no inputs for this derived value.</p>
        : (
          <ul className="derived-inputs">
            {inputs.map((input, index) => (
              <li key={`${input.field}-${index}`}>
                <b>{input.field}</b> — {inputLine(input)}{' '}
                <EvidenceClassBadge evidenceClass={input.evidenceClass} declaredClass={input.declaredClass} />
              </li>
            ))}
          </ul>
        )}
    </details>
  )
}
