import { EVIDENCE_CLASS_DESCRIPTIONS, EVIDENCE_CLASS_LABELS, EVIDENCE_CLASS_LEGEND, unrecognisedClassReason } from './evidenceClass'
import { deliveryKindDescription, deliveryKindLabel } from './deliveryKind'
import type { DeliveryKind, FieldAlternative, FieldAttribution, ResolvedEvidenceClass } from './types'

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

/** How the value reached this deployment, beside the class badge.
 *
 *  Renders nothing when the record declared no kind. That is deliberate and
 *  is the one silent absence in this interface: the delivery kind is a
 *  registry attribute, so a record that has not declared one is a gap in the
 *  registry rather than a failure of the evidence, and a "delivery unknown"
 *  chip beside a good retrieved value would read as doubt about the value. */
export function DeliveryKindLabel({ kind, intermediary }: { kind: DeliveryKind | null; intermediary: string | null }) {
  const label = deliveryKindLabel(kind, intermediary)
  if (!label || !kind) return null
  return (
    <em className={`delivery-kind delivery-kind-${kind}`} data-delivery-kind={kind} title={deliveryKindDescription(kind, intermediary) ?? undefined}>
      {label}
    </em>
  )
}

/** The badge for a field, from its attribution, with the delivery label beside
 *  it. Nothing is rendered without an attribution: there is then no value on
 *  screen to qualify. */
export function FieldEvidenceClass({ attribution }: { attribution: FieldAttribution | undefined }) {
  if (!attribution) return null
  return (
    <>
      <EvidenceClassBadge evidenceClass={attribution.evidenceClass} declaredClass={attribution.declaredClass} />
      <DeliveryKindLabel kind={attribution.deliveryKind} intermediary={attribution.intermediary} />
    </>
  )
}

/** Values the same field carried that may not be its reading.
 *
 *  Rendered under the metric, never inside it: a reprocessed or
 *  intermediary-derived value is evidence a reader may want, and refusing to
 *  show it at all would hide a retrieval, but it must never occupy the slot a
 *  producer's own published cell occupies. Each carries its class badge, its
 *  delivery label, and — where its intermediary documents nothing — the fact
 *  that the transformation is undocumented rather than absent. */
export function FieldAlternatives({ label, alternatives }: { label: string; alternatives: FieldAlternative[] | undefined }) {
  if (!alternatives || alternatives.length === 0) return null
  return (
    <details className="field-alternatives">
      <summary>{label}: {alternatives.length} alternative reading{alternatives.length === 1 ? '' : 's'}</summary>
      <p>Shown but never the reading: these values were transformed or computed by someone other than the producer, or come from a source the registry refuses as a primary.</p>
      <ul>
        {alternatives.map((alternative, index) => (
          <li key={`${alternative.attribution.sourceId ?? 'unnamed'}-${index}`}>
            <b>{alternative.text}</b>{' — '}
            {alternative.attribution.sourceId ?? alternative.attribution.product ?? alternative.attribution.provider}
            {' '}
            <EvidenceClassBadge evidenceClass={alternative.attribution.evidenceClass} declaredClass={alternative.attribution.declaredClass} />
            <DeliveryKindLabel kind={alternative.attribution.deliveryKind} intermediary={alternative.attribution.intermediary} />
            {(alternative.attribution.deliveryKind === 'reprocessed' || alternative.attribution.deliveryKind === 'intermediary_derived') && (
              <small className="alternative-method">
                {alternative.attribution.intermediaryMethod
                  ? ` Method: ${alternative.attribution.intermediaryMethod}`
                  : ' The intermediary documents no method for this field, so the transformation is undocumented rather than absent.'}
              </small>
            )}
          </li>
        ))}
      </ul>
    </details>
  )
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
