import { CATALOGUE_FAMILIES, CATALOGUE_FIELDS, FIELD_CATALOGUE_COPY, type CatalogueFieldCopy } from './fieldFamilies'
import type { ComparabilityPair, FieldPhase, FieldStorage } from './types'

/** Where a value whose response declared no family is grouped.
 *
 *  Never a guess. A family is a catalogue statement about what a quantity IS,
 *  and reading one off the spelling of a key is exactly the collision this
 *  change exists to remove: `total_cloud` looked like one field across three
 *  producers and was three quantities. So an absent `family` groups here, under
 *  a heading that says the response did not declare one. */
export const UNGROUPED_FAMILY = 'ungrouped'

/** The family a served value belongs to, from the response and nothing else. */
export function resolveFamily(declared: unknown): string {
  return typeof declared === 'string' && declared.trim().length > 0 ? declared.trim() : UNGROUPED_FAMILY
}

/** The catalogue key a value carries, verbatim, or null. */
export function resolveFieldKey(declared: unknown): string | null {
  return typeof declared === 'string' && declared.trim().length > 0 ? declared.trim() : null
}

/** Where a field's data sits, as the catalogue's storage rule declares it.
 *  Three answers, and only these three; anything else is null, which is a
 *  record that has not declared one rather than a fourth state. */
export const FIELD_STORAGES: readonly FieldStorage[] = ['stored', 'available-not-stored', 'not-published'] as const

export function resolveStorage(declared: unknown): FieldStorage | null {
  return typeof declared === 'string' && (FIELD_STORAGES as readonly string[]).includes(declared) ? (declared as FieldStorage) : null
}

export const PHASES: readonly FieldPhase[] = ['liquid', 'mixed'] as const

export function resolvePhase(declared: unknown): FieldPhase | null {
  return typeof declared === 'string' && (PHASES as readonly string[]).includes(declared) ? (declared as FieldPhase) : null
}

export const STORAGE_LABELS: Record<FieldStorage, string> = {
  stored: 'stored',
  'available-not-stored': 'available upstream · not stored',
  'not-published': 'not published by this source',
}

/** One sentence per storage answer.
 *
 *  These are deliberately three different claims about three different worlds,
 *  and each says who is responsible: the producer publishes it and we do not
 *  keep it; the producer does not publish it at all; we hold it. None of them
 *  is an absence of a VALUE — a stored field can still come back `null`,
 *  `blocked` or `aged_out`, and those are answered separately by
 *  `absenceStateSentence` so the two axes never collapse into one "no data". */
export const STORAGE_DESCRIPTIONS: Record<FieldStorage, string> = {
  stored: 'This deployment stores this field, so a value can be served for it.',
  'available-not-stored': 'The producer publishes this field and this deployment does not store it. No value is shown because none was fetched — not because none exists upstream.',
  'not-published': 'This source does not publish this field at all. Nothing upstream to fetch, and no value will ever be served for it from here.',
}

/** Why a field the interface stores still shows no number.
 *
 *  Kept apart from storage, and apart from each other: `null` is a gap the
 *  producer left, `blocked` is a credential or licence wall, `aged_out` is a
 *  value we held and purged. A reader who cannot tell those apart cannot tell
 *  whether waiting, asking for access, or nothing at all would help. */
export type AbsenceState = 'null' | 'blocked' | 'aged_out'

export const ABSENCE_STATES: readonly AbsenceState[] = ['null', 'blocked', 'aged_out'] as const

export function resolveAbsenceState(declared: unknown): AbsenceState | null {
  return typeof declared === 'string' && (ABSENCE_STATES as readonly string[]).includes(declared) ? (declared as AbsenceState) : null
}

export const ABSENCE_STATE_DESCRIPTIONS: Record<AbsenceState, string> = {
  null: 'The producer published this field here and left this value empty. It is stored, and this instant simply carries no number.',
  blocked: 'Retrieval is blocked by a credential, licence or partnership condition. The field exists and this deployment may not fetch it.',
  aged_out: 'This value was retrieved once and has left the retention window. It is not missing upstream; it is no longer held here.',
}

/** What a field shows instead of a value, in one sentence, or null when it has
 *  a value to show. Storage is answered first because it decides whether a
 *  value could exist here at all. */
export function unavailableSentence(storage: FieldStorage | null, absence: AbsenceState | null): string | null {
  if (storage === 'available-not-stored' || storage === 'not-published') return STORAGE_DESCRIPTIONS[storage]
  if (absence) return ABSENCE_STATE_DESCRIPTIONS[absence]
  return null
}

/** The family's title in the catalogue's words, or the declared name itself
 *  when the copy does not know it — a family the client cannot name is still
 *  shown under the name the response used, never folded into ungrouped. */
export function familyTitle(family: string): string {
  if (family === UNGROUPED_FAMILY) return 'Ungrouped'
  return CATALOGUE_FAMILIES[family]?.title ?? family
}

/** The family's comparability note: which members may be compared and why. */
export function familyNote(family: string): string | null {
  if (family === UNGROUPED_FAMILY) {
    return 'The response declared no field family for these values. They are listed together because nothing groups them, not because they are related, and no two of them may be compared on that basis.'
  }
  return CATALOGUE_FAMILIES[family]?.note ?? null
}

export function catalogueField(key: string | null): CatalogueFieldCopy | null {
  return key ? CATALOGUE_FIELDS[key] ?? null : null
}

/** A member's definition beside its key. The catalogue's own description, its
 *  quantity, unit and level; when the copy has never heard of the key, that is
 *  said rather than described. */
export function fieldDefinition(key: string | null): string {
  if (!key) return 'The response carried no catalogue key for this value, so no definition can be shown for it.'
  const field = catalogueField(key)
  if (!field) return `The field catalogue copy in this interface has no entry for ${key}, so no definition is shown for it.`
  const level = field.level ? ` at ${field.level}` : ''
  return `${field.description} (${field.quantity}${level}, ${field.units})`
}

/** The catalogue's comparability group for a key: which definition of the
 *  family's quantity this member measures. A catalogue lookup by exact key,
 *  never a reading of how the key is spelled. Null when the copy has no entry. */
export function catalogueComparabilityGroup(key: string | null): string | null {
  return catalogueField(key)?.comparabilityGroup ?? null
}

/** That group's definition in the catalogue's words, for the legend. This is
 *  what has to change when the map switches between two members: the ramp is
 *  drawn against a definition, and the definition is the thing that differs. */
export function comparabilityGroupDefinition(family: string, key: string | null): string | null {
  const group = catalogueComparabilityGroup(key)
  if (!group) return null
  return CATALOGUE_FAMILIES[family]?.groups?.[group] ?? null
}

/** Whether two catalogue keys measure the same definition of a family's
 *  quantity, from the catalogue copy alone — the only comparability statement
 *  available for LAYERS, since `/layers` serves no comparability list.
 *
 *  Three answers, and only `same` permits one ramp. `unstated` covers a key the
 *  copy does not know: an unknown definition is not a matching one. */
export function layerComparability(a: string | null, b: string | null): 'same' | 'different' | 'unstated' {
  const groupA = catalogueComparabilityGroup(a)
  const groupB = catalogueComparabilityGroup(b)
  if (!groupA || !groupB) return 'unstated'
  return groupA === groupB ? 'same' : 'different'
}

/** The family order the interface renders in: the catalogue's own order, then
 *  any family the copy does not know, then ungrouped last. */
export const CATALOGUE_FAMILY_ORDER: readonly string[] = FIELD_CATALOGUE_COPY.families.map((family) => family.name)

export function familyRank(family: string): number {
  if (family === UNGROUPED_FAMILY) return CATALOGUE_FAMILY_ORDER.length + 1
  const index = CATALOGUE_FAMILY_ORDER.indexOf(family)
  return index === -1 ? CATALOGUE_FAMILY_ORDER.length : index
}

export interface FamilyGroup<T> {
  family: string
  title: string
  note: string | null
  members: T[]
}

/** Group anything that names a family into family sections. Order is the
 *  catalogue's; members keep the order they were given, which is the order the
 *  response listed them. */
export function groupByFamily<T>(items: readonly T[], familyOf: (item: T) => string): Array<FamilyGroup<T>> {
  const groups = new Map<string, T[]>()
  for (const item of items) {
    const family = familyOf(item)
    const bucket = groups.get(family)
    if (bucket) bucket.push(item)
    else groups.set(family, [item])
  }
  return [...groups.entries()]
    .sort(([a], [b]) => familyRank(a) - familyRank(b) || a.localeCompare(b))
    .map(([family, members]) => ({ family, title: familyTitle(family), note: familyNote(family), members }))
}

/** Comparability as the response states it, looked up by unordered pair.
 *
 *  The API computes it — the phase rule needs the air temperature and the
 *  catalogue's definitions, neither of which the client has — so this is a
 *  lookup, never a computation. A pair the response did not answer is
 *  `undefined`: unknown, which is not the same as comparable. */
export type ComparabilityIndex = ReadonlyMap<string, ComparabilityPair>

function pairKey(a: string, b: string): string {
  return a < b ? `${a} ${b}` : `${b} ${a}`
}

export function buildComparabilityIndex(pairs: readonly ComparabilityPair[]): ComparabilityIndex {
  const index = new Map<string, ComparabilityPair>()
  for (const pair of pairs) index.set(pairKey(pair.a, pair.b), pair)
  return index
}

export function comparabilityOf(index: ComparabilityIndex, a: string | null, b: string | null): ComparabilityPair | null {
  if (!a || !b || a === b) return null
  return index.get(pairKey(a, b)) ?? null
}

/** Whether two members may be drawn as one thing. Three answers, and only the
 *  first permits it: the response said comparable; the response said not, with
 *  a reason; the response said nothing about this pair. */
export type ComparabilityVerdict = 'comparable' | 'not-comparable' | 'unstated'

export function comparabilityVerdict(index: ComparabilityIndex, a: string | null, b: string | null): ComparabilityVerdict {
  const pair = comparabilityOf(index, a, b)
  if (!pair) return 'unstated'
  return pair.comparable ? 'comparable' : 'not-comparable'
}

/** The response's own reason a pair is not comparable, in the response's own
 *  words. Never a sentence this client wrote about physics it did not check. */
export function comparabilityReason(pair: ComparabilityPair): string {
  const reason = pair.reason ?? 'no reason'
  return pair.detail ? `${reason}: ${pair.detail}` : reason
}

/** Why a difference between two members is refused, or null when it is not.
 *
 *  A refusal is a sentence, never a number. An unstated pair is refused too:
 *  the interface has no statement that the two are comparable, and subtracting
 *  on the strength of a missing field is how a difference of two definitions
 *  gets presented as a forecast disagreement. */
export function differenceRefusal(index: ComparabilityIndex, a: string | null, b: string | null): string | null {
  if (!a || !b) return 'A difference needs two members, each carrying its catalogue key. One of these carried none.'
  if (a === b) return 'A member cannot be differenced against itself.'
  const pair = comparabilityOf(index, a, b)
  if (!pair) {
    return `No comparability statement was served for ${a} and ${b}, so no difference is shown. An unstated pair is not a comparable one.`
  }
  if (pair.comparable) return null
  return `${a} and ${b} are not comparable — ${comparabilityReason(pair)}. No difference is computed: subtracting two definitions of a quantity produces a number about the definitions, not about the weather.`
}
