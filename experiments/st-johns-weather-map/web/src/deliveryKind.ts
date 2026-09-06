import type { DeliveryKind } from './types'

/** How a source's values reach this deployment, as the registry declares it.
 *
 *  A second axis from the evidence class, deliberately: an
 *  `intermediary_derived` value is still RETRIEVED by this deployment, and
 *  collapsing the two would lose the distinction between who computed a
 *  number and how it travelled here. */
export const DELIVERY_KINDS: readonly DeliveryKind[] = ['published_cell', 'reprocessed', 'intermediary_derived'] as const

export function resolveDeliveryKind(value: unknown): DeliveryKind | null {
  return typeof value === 'string' && (DELIVERY_KINDS as readonly string[]).includes(value) ? (value as DeliveryKind) : null
}

/** The intermediary's name, or an honest stand-in.
 *
 *  A record that declares a third-party kind and names nobody fails the
 *  registry audit, so this should be unreachable from a valid registry. If it
 *  is ever reached, the label says the intermediary is unnamed rather than
 *  quietly reading as the producer's own. */
function party(intermediary: string | null): string {
  return intermediary ?? 'an unnamed intermediary'
}

/** The label rendered beside the class badge, or null.
 *
 *  Null means the record declared no kind. That renders NO label: the kind is
 *  a registry attribute, and a record that has not declared one yet is a gap
 *  in the registry, not a failure of the evidence. This is the one place in
 *  this interface where an absent declaration is silent, and it is silent
 *  because saying "delivery unknown" beside a perfectly good retrieved value
 *  would read as a doubt about the value. */
export function deliveryKindLabel(kind: DeliveryKind | null, intermediary: string | null): string | null {
  if (kind === 'published_cell') return "producer's own cell"
  if (kind === 'reprocessed') return `reprocessed by ${party(intermediary)}`
  if (kind === 'intermediary_derived') return `computed by ${party(intermediary)}`
  return null
}

/** The same statement as a sentence, for the text alternative and the
 *  catalogue, where there is room to say what the kind means. */
export function deliveryKindDescription(kind: DeliveryKind | null, intermediary: string | null): string | null {
  if (kind === 'published_cell') return "The producer's own grid cell or observation, retrieved as issued."
  if (kind === 'reprocessed') return `${party(intermediary)} transformed the producer's field before delivering it.`
  if (kind === 'intermediary_derived') return `${party(intermediary)} computed this from the producer's fields by its own method.`
  return null
}
