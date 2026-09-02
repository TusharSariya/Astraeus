/** For the selected instant, every source the API reports as covering it
 *  (task 4.2): the `coverage` array of the hourly `/timeline` item
 *  containing that instant, floored to the hour in UTC. Three distinct
 *  empty states, worded differently so none is mistaken for another:
 *  (a) `coverage: []` — "Nothing covers this instant"; (b) the request
 *  failed or the item carries no `coverage` array (older API / unrecognised
 *  shape) — "Coverage unavailable: <reason>", claiming nothing either way;
 *  (c) a source that covers the instant but whose frame published no value
 *  is not this panel's concern and is never conflated with (a). Nobody is
 *  marked primary; order is exactly the API's (source_id then run_time). */

import { stJohnsTime } from './api'
import type { CoverageEntry, TimelineItem, TimelineResponse } from './types'

export interface CoveragePanelProps {
  timeline: TimelineResponse | null
  timelineError: string | null
  selectedMs: number
}

/** The hourly item containing `atMs`, floored to the hour in UTC. Null when
 *  no item's `valid_time_utc` lands on that hour. */
export function timelineItemForInstant(items: TimelineItem[], atMs: number): TimelineItem | null {
  const hourMs = Math.floor(atMs / 3_600_000) * 3_600_000
  for (const item of items) {
    const stamp = new Date(item.valid_time_utc).getTime()
    if (!Number.isNaN(stamp) && stamp === hourMs) return item
  }
  return null
}

export type CoverageState =
  | { kind: 'entries'; entries: CoverageEntry[] }
  | { kind: 'empty'; notice: string | null }
  | { kind: 'unavailable'; reason: string }

/** Which of the three states applies. A failed timeline request, a missing
 *  timeline, or an item with no `coverage` array at all (an older API, or a
 *  shape this client does not recognise) are all "unavailable" — the panel
 *  never reads a missing array as an empty one, because those are different
 *  claims. */
export function resolveCoverageState(
  timeline: TimelineResponse | null,
  timelineError: string | null,
  item: TimelineItem | null,
): CoverageState {
  if (!timeline || timelineError) {
    return { kind: 'unavailable', reason: timelineError ?? 'the timeline request failed' }
  }
  if (!item || !Array.isArray(item.coverage)) {
    return { kind: 'unavailable', reason: 'no coverage array published for this instant (older API or unrecognised shape)' }
  }
  if (item.coverage.length === 0) return { kind: 'empty', notice: item.coverage_notice ?? null }
  return { kind: 'entries', entries: item.coverage }
}

/** The frame offset the spec asks for: selected instant minus run time,
 *  signed, in the same magnitude buckets `describeOffset` uses elsewhere —
 *  but worded around what the sign here actually means (a run's age
 *  relative to the selection), never reusing `describeOffset`'s "later"
 *  wording, which is written for a frame's own time relative to a request
 *  and would read backwards for a run time. */
function formatRunOffset(runTimeIso: string, selectedMs: number): string {
  const offsetSeconds = Math.round((selectedMs - new Date(runTimeIso).getTime()) / 1000)
  if (offsetSeconds === 0) return 'run time equals the selected instant'
  const magnitude = Math.abs(offsetSeconds)
  const amount = magnitude < 90 ? `${magnitude} s` : magnitude < 5400 ? `${Math.round(magnitude / 60)} min` : `${(magnitude / 3600).toFixed(1)} h`
  return offsetSeconds > 0 ? `run started ${amount} before the selected instant` : `run started ${amount} after the selected instant`
}

function runAgeWords(entry: CoverageEntry): string {
  if (entry.run_age_seconds === null || entry.run_age_seconds === undefined) return ''
  const hours = entry.run_age_seconds / 3600
  return hours >= 1 ? ` · ${hours.toFixed(1)} h old` : ` · ${Math.round(entry.run_age_seconds / 60)} min old`
}

export function CoveragePanel({ timeline, timelineError, selectedMs }: CoveragePanelProps) {
  const item = timeline ? timelineItemForInstant(timeline.items, selectedMs) : null
  const state = resolveCoverageState(timeline, timelineError, item)
  return (
    <section className="coverage-panel" aria-label="Sources covering the selected instant">
      <h3 className="coverage-panel-title">Coverage at this instant</h3>
      {state.kind === 'unavailable' && (
        <p className="coverage-notice coverage-unavailable">Coverage unavailable: {state.reason}</p>
      )}
      {state.kind === 'empty' && (
        <p className="coverage-notice coverage-empty">
          Nothing covers this instant{state.notice ? ` — ${state.notice}` : ''}
        </p>
      )}
      {state.kind === 'entries' && (
        <ul className="coverage-list">
          {state.entries.map((entry, index) => (
            <li key={`${entry.source_id}-${entry.provider_run_id}-${index}`} className="coverage-entry">
              <span className="coverage-source">{entry.source_id}</span>
              {entry.run_time ? (
                <span className="coverage-run">
                  run {stJohnsTime(entry.run_time)} NT ({entry.run_time} UTC) · {formatRunOffset(entry.run_time, selectedMs)}
                </span>
              ) : (
                <span className="coverage-run">run time unknown</span>
              )}
              {entry.run_stale === true && (
                <span className="coverage-stale-badge" data-run-stale="true">
                  run_stale{runAgeWords(entry)}
                </span>
              )}
              {entry.run_stale === null && (
                <span className="coverage-stale-unknown" data-run-stale="unknown">
                  run staleness unknown: {entry.run_stale_reason ?? 'reason not stated'}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
