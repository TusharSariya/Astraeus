import { useMemo, useState } from 'react'
import {
  UNGROUPED_FAMILY,
  buildComparabilityIndex,
  comparabilityOf,
  comparabilityReason,
  differenceRefusal,
  fieldDefinition,
  groupByFamily,
  resolveAbsenceState,
  unavailableSentence,
  type ComparabilityIndex,
} from './fieldFamily'
import { STORAGE_DESCRIPTIONS, STORAGE_LABELS } from './fieldFamily'
import { EvidenceClassBadge } from './EvidenceClassBadge'
import type { CatalogSource, ComparabilityPair, EvidenceSnapshot, ServedFieldValue } from './types'

/** The value's own storage line, or null.
 *
 *  `stored` renders no line: it is the ordinary case and a label on every
 *  reading would be noise. The two that are NOT stored always render, because
 *  each explains an absent number that would otherwise read as a failure. */
function StorageLine({ member }: { member: ServedFieldValue }) {
  const storage = member.attribution.storage
  if (!storage || storage === 'stored') return null
  return (
    <p className={`family-storage storage-${storage}`} data-storage={storage}>
      <b>{STORAGE_LABELS[storage]}</b> — {STORAGE_DESCRIPTIONS[storage]}
    </p>
  )
}

/** What a member shows where a number would go.
 *
 *  Five different answers, kept apart on purpose: a value; `available-not-stored`
 *  and `not-published`, which are upstream facts; and `null`, `blocked` or
 *  `aged_out`, which are absences of a value in a field this deployment does
 *  hold. Collapsing any of them into "no data" would tell a reader nothing
 *  about whether waiting, asking for access, or nothing at all would help. */
function memberValueText(member: ServedFieldValue): string {
  if (member.hasValue) return member.text
  const storage = member.attribution.storage
  if (storage === 'available-not-stored') return 'Not stored here'
  if (storage === 'not-published') return 'Not published by this source'
  const absence = resolveAbsenceState(member.attribution.qualityStatus)
  if (absence === 'blocked') return 'Blocked'
  if (absence === 'aged_out') return 'Aged out of the retention window'
  return 'No value'
}

function MemberRow({ member, index }: { member: ServedFieldValue; index: ComparabilityIndex }) {
  const key = member.attribution.fieldKey
  const absence = member.hasValue ? null : resolveAbsenceState(member.attribution.qualityStatus)
  const sentence = member.hasValue ? null : unavailableSentence(member.attribution.storage, absence)
  // Which siblings this member may NOT be drawn with, named on the member
  // itself so the statement travels with the value rather than living only in
  // a family heading a reader may have scrolled past.
  const conflicts = key ? [...index.values()].filter((pair) => !pair.comparable && (pair.a === key || pair.b === key)) : []
  return (
    <li className="family-member" data-field-key={key ?? ''} data-family={member.attribution.family}>
      <p className="family-member-head">
        <code className="family-member-key">{key ?? 'no catalogue key'}</code>
        <strong className="family-member-value">{memberValueText(member)}</strong>
        {member.attribution.phase && <span className="family-member-phase" data-phase={member.attribution.phase}>phase: {member.attribution.phase}</span>}
        <EvidenceClassBadge evidenceClass={member.attribution.evidenceClass} declaredClass={member.attribution.declaredClass} />
        <em className="family-member-source">{member.attribution.sourceId ?? member.attribution.product ?? member.attribution.provider}</em>
      </p>
      <p className="family-member-definition">{fieldDefinition(key)}</p>
      <StorageLine member={member} />
      {sentence && !member.attribution.storage && <p className="family-member-absence">{sentence}</p>}
      {member.attribution.uncatalogued && (
        <p className="family-member-uncatalogued">
          This variable has no catalogue key, so no value is served for it and it belongs to no family.
          {member.attribution.notice ? ` ${member.attribution.notice}` : ' The response gave no further reason.'}
        </p>
      )}
      {conflicts.map((pair) => (
        <p key={`${pair.a}|${pair.b}`} className="family-not-comparable" data-not-comparable={`${pair.a}|${pair.b}`}>
          Not comparable with {pair.a === key ? pair.b : pair.a} — {comparabilityReason(pair)}. The two are never drawn on one
          ramp, one axis or one difference.
        </p>
      ))}
    </li>
  )
}

/** Every served value under the family the response put it in.
 *
 *  The grouping is the response's `family` and nothing else. A value that
 *  declared none lands under "Ungrouped", which says so — rather than being
 *  filed next to something that merely looks like it. */
export function FieldFamilyGroups({ snapshot }: { snapshot: EvidenceSnapshot }) {
  const index = useMemo(() => buildComparabilityIndex(snapshot.comparability), [snapshot.comparability])
  const groups = useMemo(() => groupByFamily(snapshot.servedFields, (member) => member.attribution.family), [snapshot.servedFields])
  // Nothing to group by, nothing to show. Against a response that declares no
  // family and no key on any value — the API before section 3 lands — this
  // whole panel would be one "Ungrouped" list repeating the metrics with no
  // catalogue statement attached to any of them, which teaches a reader
  // nothing and hides the metrics behind noise. The absence of the panel is
  // itself accurate: no family has been declared for anything.
  const declaresCatalogue = snapshot.servedFields.some((member) => member.attribution.fieldKey !== null || member.attribution.family !== UNGROUPED_FAMILY)
  if (groups.length === 0 || !declaresCatalogue) return null
  return (
    <section className="field-families evidence-surface" aria-label="Readings by field family">
      <h3>Readings by field family</h3>
      <p>
        A family groups fields that measure related but non-identical quantities. Members are listed under the family the
        response declared for each value, with its catalogue key and the catalogue&apos;s definition. Two members are drawn
        as one thing only where the response states they are comparable.
      </p>
      {groups.map((group) => (
        <section
          key={group.family}
          className={`field-family family-${group.family}`}
          aria-label={`${group.title} family`}
          data-family={group.family}
        >
          <h4>{group.title}{group.family === UNGROUPED_FAMILY ? '' : ` · ${group.family}`}</h4>
          {group.note && <p className="family-note">{group.note}</p>}
          <ul className="family-members">
            {group.members.map((member, position) => (
              <MemberRow key={`${member.field}-${member.attribution.sourceId ?? position}`} member={member} index={index} />
            ))}
          </ul>
        </section>
      ))}
    </section>
  )
}

/** What each catalogued source publishes, key by key, grouped by family.
 *
 *  This is where `available-not-stored` earns its place: a reader looking for
 *  a GFS field that shows no value on the page can see that the producer does
 *  publish it and this deployment does not fetch it, which is a different fact
 *  from the field being absent, blocked, or aged out of the store. */
export function SourceFieldCatalogue({ sources }: { sources: CatalogSource[] }) {
  const withFields = sources.filter((source) => Array.isArray(source.fields) && source.fields.length > 0)
  if (withFields.length === 0) return null
  return (
    <section className="source-field-catalogue" aria-label="Fields by source and family">
      <h4>Fields by source and family</h4>
      {withFields.map((source) => (
        <details key={source.id} className="source-fields">
          <summary>{source.producer} · {source.product} — {source.fields!.length} catalogued fields</summary>
          {groupByFamily(source.fields!, (entry) => entry.family || UNGROUPED_FAMILY).map((group) => (
            <div key={group.family} className="source-family" data-family={group.family}>
              <h5>{group.title}</h5>
              <ul>
                {group.members.map((entry) => (
                  <li key={entry.key} data-field-key={entry.key} data-storage={entry.storage ?? ''}>
                    <code>{entry.key}</code>
                    {entry.storage && <> · <b>{STORAGE_LABELS[entry.storage]}</b></>}
                    {entry.upstream && <> · upstream <code>{entry.upstream}</code></>}
                    <br />
                    {entry.storage && entry.storage !== 'stored' ? STORAGE_DESCRIPTIONS[entry.storage] : fieldDefinition(entry.key)}
                    {entry.note ? ` ${entry.note}` : ''}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </details>
      ))}
    </section>
  )
}

/** One option in the difference selectors: a served member that carries a key. */
interface DifferenceOption {
  id: string
  key: string
  label: string
  member: ServedFieldValue
}

function differenceOptions(snapshot: EvidenceSnapshot): DifferenceOption[] {
  return snapshot.servedFields
    .map((member, position) => {
      const key = member.attribution.fieldKey
      if (!key) return null
      const source = member.attribution.sourceId ?? member.attribution.product ?? member.attribution.provider
      return { id: `${position}`, key, label: `${key} · ${source}`, member }
    })
    .filter((option): option is DifferenceOption => option !== null)
}

/** The pairs the response declared non-comparable, for the standing statement
 *  the panel shows before anyone asks for a difference. */
function refusedPairs(comparability: readonly ComparabilityPair[]): ComparabilityPair[] {
  return comparability.filter((pair) => !pair.comparable)
}

/** Ask for a difference between two members; get a number or a reason.
 *
 *  The refusal is the point. HRDPS opacity-weighted cloud minus GFS geometric
 *  cloud is arithmetic that produces a number about two definitions, and a
 *  reader looking at it would read a model disagreement. So a pair the response
 *  did not state comparable is answered with the reason, never with a value —
 *  and an unstated pair is refused too, because silence is not permission. */
export function DifferenceView({ snapshot }: { snapshot: EvidenceSnapshot }) {
  const options = useMemo(() => differenceOptions(snapshot), [snapshot])
  const index = useMemo(() => buildComparabilityIndex(snapshot.comparability), [snapshot.comparability])
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [asked, setAsked] = useState(false)
  if (options.length < 2) return null
  const left = options.find((option) => option.id === a) ?? null
  const right = options.find((option) => option.id === b) ?? null
  const refusal = asked ? differenceRefusal(index, left?.key ?? null, right?.key ?? null) : null
  const pair = left && right ? comparabilityOf(index, left.key, right.key) : null
  const numeric = left?.member.value !== null && left?.member.value !== undefined && right?.member.value !== null && right?.member.value !== undefined
  const sameUnits = left?.member.units === right?.member.units
  const difference = asked && !refusal && left && right && numeric && sameUnits
    ? `${(left.member.value! - right.member.value!).toFixed(1)}${left.member.units ? ` ${left.member.units}` : ''}`
    : null
  return (
    <section className="difference-view evidence-surface" aria-label="Difference between two family members">
      <h3>Difference between two members</h3>
      <p>
        Choose two served members. A difference is shown only where the response states the pair is comparable; otherwise
        the reason is shown in place of a number.
      </p>
      {refusedPairs(snapshot.comparability).map((entry) => (
        <p key={`${entry.a}|${entry.b}`} className="difference-standing-refusal">
          {entry.a} and {entry.b} are not comparable — {comparabilityReason(entry)}.
        </p>
      ))}
      <label>
        Minuend
        <select aria-label="Difference member A" value={a} onChange={(event) => { setA(event.target.value); setAsked(false) }}>
          <option value="">Choose a member</option>
          {options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
        </select>
      </label>
      <label>
        Subtrahend
        <select aria-label="Difference member B" value={b} onChange={(event) => { setB(event.target.value); setAsked(false) }}>
          <option value="">Choose a member</option>
          {options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
        </select>
      </label>
      <button type="button" onClick={() => setAsked(true)} disabled={!left || !right}>Show difference</button>
      {asked && refusal && (
        <p className="difference-refused" role="status" data-difference="refused">Difference refused: {refusal}</p>
      )}
      {asked && !refusal && difference && (
        <p className="difference-value" role="status" data-difference="shown">
          {left?.key} minus {right?.key} = {difference}
          {pair && <> · the response states this pair is comparable</>}
        </p>
      )}
      {asked && !refusal && !difference && (
        <p className="difference-refused" role="status" data-difference="refused">
          Difference not shown: the pair is comparable, but {numeric ? 'the two values were served in different units' : 'at least one member carried no number'}.
          Nothing is converted or assumed here.
        </p>
      )}
    </section>
  )
}
