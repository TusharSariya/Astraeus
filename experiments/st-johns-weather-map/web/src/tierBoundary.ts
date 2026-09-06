/** Pure geometry for the horizon-tiers scrubber (task 4.1): the window
 *  `/timeline` states, the 24 h boundary's position and text alternative,
 *  the scale marks either side of it, and whether the planning tier has
 *  anything published. Kept out of TimelineDock so it is testable without a
 *  DOM — see design.md's Seam: "the scrubber spans `/timeline` `start..end`
 *  ... the boundary is `timeline.boundary`". */

import type { ScaleMark } from './scrubberAxis'
import type { TierRange, TimelineItem } from './types'

/** The window's fallback span when `/timeline` is unavailable: 24 h back to
 *  14 d ahead — the two tiers' combined range named in
 *  `evidence-window-timeline`. This replaces the old fixed 3 h/24 h span. */
export const FALLBACK_BACK_MINUTES = 24 * 60
export const FALLBACK_FORWARD_MINUTES = 14 * 24 * 60

export interface WindowBounds {
  backMinutes: number
  forwardMinutes: number
}

/** The scrubber's window: `/timeline` `start..end` relative to `reference`
 *  when the timeline is available and its bounds parse, else the fallback
 *  constants above. Negative spans (a malformed or reversed window) are
 *  clamped to zero rather than drawing a scrubber that runs backwards. */
export function windowFromTimeline(
  timeline: { start: string; end: string } | null | undefined,
  reference: Date,
): WindowBounds {
  const fallback: WindowBounds = { backMinutes: FALLBACK_BACK_MINUTES, forwardMinutes: FALLBACK_FORWARD_MINUTES }
  if (!timeline) return fallback
  const startMs = new Date(timeline.start).getTime()
  const endMs = new Date(timeline.end).getTime()
  if (Number.isNaN(startMs) || Number.isNaN(endMs)) return fallback
  const refMs = reference.getTime()
  return {
    backMinutes: Math.max(0, Math.round((refMs - startMs) / 60_000)),
    forwardMinutes: Math.max(0, Math.round((endMs - refMs) / 60_000)),
  }
}

/** The scale marks either side of the boundary: hourly-ish inside the 24 h
 *  core tier, daily beyond it — the step change made visible on the axis
 *  itself, not only at the boundary tick. `placeScaleMarks` still owns
 *  collision handling; this only supplies the candidate set. */
export const HORIZON_SCALE_MARKS: readonly ScaleMark[] = [
  { hours: -24, label: '-24h', short: '-24h' },
  { hours: -12, label: '-12h', short: '-12h' },
  { hours: 0, label: 'Now', short: 'Now' },
  { hours: 6, label: '+6h', short: '+6h' },
  { hours: 12, label: '+12h', short: '+12h' },
  { hours: 24, label: '+24h', short: '+24h' },
  { hours: 48, label: '+2d', short: '+2d' },
  { hours: 96, label: '+4d', short: '+4d' },
  { hours: 168, label: '+7d', short: '+7d' },
  { hours: 240, label: '+10d', short: '+10d' },
  { hours: 336, label: '+14d', short: '+14d' },
]

export interface BoundaryMark {
  /** Fraction of the window rail, 0..1, or null when the span is zero. */
  fraction: number
  /** The tick's own label: a tick plus a label, never colour alone. */
  label: string
  /** The text alternative naming both tier ranges, for a visually-hidden
   *  node or `aria-describedby` text beside the tick. */
  description: string
}

function rangeWords(range: TierRange | undefined, fallbackWords: string): string {
  if (!range || !range.start || !range.end) return fallbackWords
  return `${range.start} to ${range.end}`
}

/** The boundary tick's position and its text alternative, from
 *  `timeline.boundary`/`timeline.tiers` and the window the rail spans.
 *  `null` when there is no boundary to mark — an older API, or one that
 *  answered with an unparseable instant — because a mark implies a stated
 *  fact and never a guess. */
export function boundaryMark(
  boundary: string | null | undefined,
  tiers: TierRange[] | null | undefined,
  windowStartMs: number,
  windowEndMs: number,
): BoundaryMark | null {
  if (!boundary) return null
  const stamp = new Date(boundary).getTime()
  if (Number.isNaN(stamp)) return null
  const span = windowEndMs - windowStartMs
  const fraction = span > 0 ? (stamp - windowStartMs) / span : 0
  const core = tiers?.find((tier) => tier.id === 'core')
  const planning = tiers?.find((tier) => tier.id === 'planning')
  const description = `Boundary at +24h. Core tier: ${rangeWords(core, '24 h back to 24 h ahead')}. Planning tier: ${rangeWords(planning, '24 h ahead to 14 d ahead')}.`
  return { fraction, label: '+24h | planning', description }
}

/** Whether the planning tier (every item strictly past `boundary`) has at
 *  least one instant with non-empty coverage — `coverage` where the API
 *  serves it, else `available_products` for an older API. `true` (no note
 *  drawn) when `boundary` itself cannot be resolved: nothing is known about
 *  where the tiers split, so nothing is asserted about one side of it. */
export function planningTierHasCoverage(items: TimelineItem[], boundary: string | null | undefined): boolean {
  if (!boundary) return true
  const boundaryMs = new Date(boundary).getTime()
  if (Number.isNaN(boundaryMs)) return true
  return items.some((item) => {
    const stamp = new Date(item.valid_time_utc).getTime()
    if (Number.isNaN(stamp) || stamp <= boundaryMs) return false
    if (Array.isArray(item.coverage)) return item.coverage.length > 0
    return Array.isArray(item.available_products) && item.available_products.length > 0
  })
}
