import type { EnsembleMemberSet, EnsembleProvenance, EvidenceSnapshot, ServedFieldValue } from './types'

/** The response's own field key for GEFS six-hour-mean total cloud
 *  (`registry/fields.py`, task 2.3). The fence below also catches any value
 *  whose `ensemble.averaging_window_hours` is set, so a family that ships the
 *  window without this exact key still lands in the averaged group. */
const AVERAGED_CLOUD_FIELD_KEY = 'total_cloud_mean_6h'

/** Whether a served field carries any ensemble identity at all: a per-member
 *  value or a statistic, refused or not. Everything else — a plain
 *  deterministic reading — has `attribution.ensemble === null` and is never
 *  shown in the ensemble panel or counted by the fence. */
export function isEnsembleField(field: ServedFieldValue): boolean {
  return field.attribution.ensemble !== null
}

/** The fence: true only for a value whose window is named, either on the
 *  response itself (`ensemble.averaging_window_hours`) or by its field key.
 *  Never inferred from the field's family or from a heuristic on the number —
 *  the response's own declaration is the only source. */
export function isAveragedField(field: ServedFieldValue): boolean {
  const window = field.attribution.ensemble?.averagingWindowHours
  return (typeof window === 'number' && window > 0) || field.field === AVERAGED_CLOUD_FIELD_KEY
}

/** "member 07 (control)", "member 07", or the statistic name. A value with
 *  neither is never reached here — `isEnsembleField` gates every caller. */
function memberOrStatisticLabel(field: ServedFieldValue): string {
  const ensemble = field.attribution.ensemble
  if (ensemble?.statistic) return ensemble.statistic
  if (field.attribution.member !== null) {
    return field.attribution.memberControl ? `member ${field.attribution.member} (control)` : `member ${field.attribution.member}`
  }
  return 'ensemble value with no statistic and no member named'
}

/** "18 of 21 members", with the missing ids named the moment the set is
 *  partial, never folded into a bare count that hides which members are gone. */
function memberSetLabel(memberSet: EnsembleMemberSet | null): string {
  if (!memberSet) return 'member set unknown'
  const base = `${memberSet.membersUsed} of ${memberSet.membersDeclared} members`
  if (memberSet.partial) {
    return memberSet.membersMissing.length > 0
      ? `${base} — missing ${memberSet.membersMissing.join(', ')}`
      : `${base} — partial set`
  }
  return base
}

/** "computed here" or "provider's own". Only meaningful once the row is
 *  known to be an ensemble value, so this is never called on a null ensemble. */
function computedHereLabel(ensemble: EnsembleProvenance): string {
  return ensemble.computedHere ? 'computed here' : "provider's own"
}

export type EnsembleRowKind = 'member' | 'statistic' | 'refused' | 'provider_reduction'

export interface EnsembleRow {
  key: string
  field: string
  kind: EnsembleRowKind
  averaged: boolean
  /** The full sentence: family, run, statistic-or-member, member set, and
   *  computed-here-or-provider's-own, in that order — the four (five, counting
   *  the family/run pair as two) names no ensemble number is ever shown
   *  without. Used verbatim in both the panel and the text alternative, so
   *  nothing about an ensemble number is available only visually. */
  text: string
}

/** One row per served field that carries an ensemble identity, in response
 *  order. The refusal check comes first: a refused statistic has no value and
 *  is never mistaken for a provider reduction just because `computed_here`
 *  happens to be unset on it. */
export function ensembleRowsOf(servedFields: ServedFieldValue[]): EnsembleRow[] {
  return servedFields.filter(isEnsembleField).map((field, index) => {
    const ensemble = field.attribution.ensemble as EnsembleProvenance
    const refused = field.attribution.qualityFlags.includes('statistic_refused')
    const isStatistic = ensemble.statistic !== null
    const kind: EnsembleRowKind = refused
      ? 'refused'
      : isStatistic
        ? (ensemble.computedHere ? 'statistic' : 'provider_reduction')
        : 'member'
    const family = ensemble.family
    const run = ensemble.memberSet?.runTime ?? 'run unknown'
    const nameOrStat = memberOrStatisticLabel(field)
    const setLabel = memberSetLabel(ensemble.memberSet)
    const parts = [family, `run ${run}`, nameOrStat, setLabel]
    // A refused statistic makes neither claim — it was never computed and
    // never a provider reduction, so "computed here" or "provider's own"
    // would misstate what happened. Its own refusal reason stands in for both.
    if (isStatistic && !refused) parts.push(computedHereLabel(ensemble))
    if (refused) parts.push(`refused: ${ensemble.refusal ?? 'the response gave no reason'}`)
    const averaged = isAveragedField(field)
    if (averaged) parts.push('6 h mean, not comparable with instantaneous cloud')
    // Several members of the same family and field share a source id, so the
    // member id (when there is one) joins the key; a statistic and a member
    // never collide because only one of the two ever carries a member id.
    const identity = field.attribution.member ?? ensemble.statistic ?? String(index)
    return {
      key: `${field.field}-${field.attribution.sourceId ?? 'unknown-source'}-${identity}`,
      field: field.field,
      kind,
      averaged,
      text: parts.join(' · '),
    }
  })
}

/** The averaged rows split from every other ensemble row. A time-averaged
 *  member field is never drawn beside an instantaneous one — on this panel,
 *  drawn means grouped: the two lists render as separate sections with their
 *  own heading, never interleaved in one list a reader could read as one
 *  comparable set. */
export function groupEnsembleRows(rows: EnsembleRow[]): { standard: EnsembleRow[]; averaged: EnsembleRow[] } {
  return {
    standard: rows.filter((row) => !row.averaged),
    averaged: rows.filter((row) => row.averaged),
  }
}

const KIND_LABELS: Record<EnsembleRowKind, string> = {
  member: 'Member',
  statistic: 'Statistic',
  refused: 'Refused statistic',
  provider_reduction: "Provider's own statistic",
}

/** The member and statistic rows the response served, grouped into the
 *  averaged-versus-instantaneous fence. Renders nothing where the response
 *  carries no ensemble value at all — the absence of the panel is itself
 *  accurate, matching `FieldFamilyPanel`'s rule for its own empty case. */
export function EnsemblePanel({ snapshot }: { snapshot: EvidenceSnapshot }) {
  const rows = ensembleRowsOf(snapshot.servedFields)
  if (rows.length === 0) return null
  const { standard, averaged } = groupEnsembleRows(rows)
  return (
    <section className="ensemble-panel evidence-surface" aria-label="Ensemble members and statistics">
      <h3>Ensemble members and statistics</h3>
      <p>
        Every ensemble number here names the family and run it came from, which statistic it is (or which member), the
        member set it covers, and whether it was computed here or is the provider&apos;s own reduction. A value that cannot
        be named all four ways is not shown.
      </p>
      {standard.length > 0 && (
        <ul className="ensemble-rows" data-ensemble-group="standard">
          {standard.map((row) => (
            <li key={row.key} className={`ensemble-row ensemble-row-${row.kind}`} data-ensemble-kind={row.kind} data-field={row.field}>
              <span className="ensemble-row-kind">{KIND_LABELS[row.kind]}</span>
              <span className="ensemble-row-text">{row.text}</span>
            </li>
          ))}
        </ul>
      )}
      {averaged.length > 0 && (
        <div className="ensemble-averaged-group" data-ensemble-group="averaged">
          <h4>6 h mean, not comparable with instantaneous cloud</h4>
          <ul className="ensemble-rows" data-ensemble-group="averaged">
            {averaged.map((row) => (
              <li key={row.key} className={`ensemble-row ensemble-row-${row.kind}`} data-ensemble-kind={row.kind} data-field={row.field}>
                <span className="ensemble-row-kind">{KIND_LABELS[row.kind]}</span>
                <span className="ensemble-row-text">{row.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

/** The same rows, in the text alternative's `{ label, value }` shape, so
 *  every ensemble number the map reads out carries the same four names as the
 *  panel — never available only visually. The averaged group keeps its own
 *  label rather than being merged with the standard rows under one heading. */
export function ensembleTextRows(snapshot: EvidenceSnapshot): Array<{ label: string; value: string }> {
  // `row.key` (field plus source id, or field plus index) rather than the
  // field name alone: several members of the same family report under the
  // same field name, and a label that collapsed them would render one row's
  // worth of text for several distinct ensemble values.
  return ensembleRowsOf(snapshot.servedFields).map((row) => ({
    label: `Ensemble · ${KIND_LABELS[row.kind]} · ${row.key}`,
    value: row.text,
  }))
}

/** One option for the member selector: the members the response actually
 *  served, deduplicated, each carrying whether it is the control. */
export interface EnsembleMemberOption {
  value: string
  label: string
  control: boolean
}

export function ensembleMemberOptions(snapshot: EvidenceSnapshot): EnsembleMemberOption[] {
  const seen = new Map<string, boolean>()
  snapshot.servedFields.forEach((field) => {
    const member = field.attribution.member
    if (member !== null && !seen.has(member)) seen.set(member, field.attribution.memberControl === true)
  })
  return [...seen.entries()].map(([value, control]) => ({ value, label: control ? `${value} (control)` : value, control }))
}
