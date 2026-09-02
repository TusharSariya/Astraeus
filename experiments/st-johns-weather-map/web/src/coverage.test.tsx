import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CoveragePanel, resolveCoverageState, timelineItemForInstant } from './CoveragePanel'
import type { CoverageEntry, TimelineItem, TimelineResponse } from './types'

const selectedIso = '2026-09-02T15:20:00Z'
const selectedMs = new Date(selectedIso).getTime()

function entry(overrides: Partial<CoverageEntry> = {}): CoverageEntry {
  return {
    source_id: 'eccc-hrdps', provider_run_id: 'hrdps-2026090212', run_time: '2026-09-02T12:00:00Z',
    run_cadence_seconds: 21600, run_age_seconds: 12000, run_stale: false, run_stale_reason: null,
    ...overrides,
  }
}

function timelineWith(item: Partial<TimelineItem>): TimelineResponse {
  return {
    data_mode: 'live', start: '', end: '',
    items: [{ valid_time_utc: '2026-09-02T15:00:00Z', valid_time_newfoundland: '', available_products: [], ...item }],
  }
}

describe('timelineItemForInstant: floors to the hour in UTC', () => {
  it('finds the item whose valid_time_utc is the floored hour', () => {
    const items: TimelineItem[] = [
      { valid_time_utc: '2026-09-02T14:00:00Z', valid_time_newfoundland: '', available_products: [] },
      { valid_time_utc: '2026-09-02T15:00:00Z', valid_time_newfoundland: '', available_products: [] },
    ]
    expect(timelineItemForInstant(items, selectedMs)?.valid_time_utc).toBe('2026-09-02T15:00:00Z')
  })

  it('is null when no item lands on that hour', () => {
    const items: TimelineItem[] = [{ valid_time_utc: '2026-09-02T14:00:00Z', valid_time_newfoundland: '', available_products: [] }]
    expect(timelineItemForInstant(items, selectedMs)).toBeNull()
  })
})

describe('resolveCoverageState: three distinct empty states (task 4.2)', () => {
  it('(a) coverage: [] reads "nothing covers this instant", distinct from a failed request', () => {
    const timeline = timelineWith({ coverage: [], coverage_notice: 'nothing covers this instant' })
    const state = resolveCoverageState(timeline, null, timeline.items[0])
    expect(state).toEqual({ kind: 'empty', notice: 'nothing covers this instant' })
  })

  it('(b) the timeline request failed reads "unavailable", never as empty coverage', () => {
    const state = resolveCoverageState(null, 'network error', null)
    expect(state.kind).toBe('unavailable')
    expect((state as { reason: string }).reason).toBe('network error')
  })

  it('(b) an item with no coverage array (older API / unrecognised shape) is unavailable, not empty', () => {
    const timeline = timelineWith({})
    delete (timeline.items[0] as { coverage?: unknown }).coverage
    const state = resolveCoverageState(timeline, null, timeline.items[0])
    expect(state.kind).toBe('unavailable')
  })

  it('is unavailable when no item was found for the instant at all', () => {
    const timeline = timelineWith({})
    const state = resolveCoverageState(timeline, null, null)
    expect(state.kind).toBe('unavailable')
  })

  it('lists entries, in the order the API sent them, when coverage is non-empty', () => {
    const entries = [entry({ source_id: 'a' }), entry({ source_id: 'b' })]
    const timeline = timelineWith({ coverage: entries })
    const state = resolveCoverageState(timeline, null, timeline.items[0])
    expect(state).toEqual({ kind: 'entries', entries })
  })
})

describe('CoveragePanel: rendered states', () => {
  it('several sources at one instant: all listed, none marked primary, stable order', () => {
    const entries = [
      entry({ source_id: 'eccc-hrdps', run_time: '2026-09-02T12:00:00Z' }),
      entry({ source_id: 'noaa-gfs', run_time: '2026-09-02T06:00:00Z' }),
      entry({ source_id: 'ecmwf-ifs', run_time: '2026-09-02T00:00:00Z' }),
    ]
    const timeline = timelineWith({ coverage: entries })
    render(<CoveragePanel timeline={timeline} timelineError={null} selectedMs={new Date('2026-09-02T15:00:00Z').getTime()} />)
    const list = screen.getByRole('list')
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(3)
    expect(rows.map((row) => within(row).getByText(/eccc-hrdps|noaa-gfs|ecmwf-ifs/).textContent))
      .toEqual(['eccc-hrdps', 'noaa-gfs', 'ecmwf-ifs'])
    // Nobody is marked primary: no "primary" wording anywhere in the panel.
    expect(within(list).queryByText(/primary/i)).not.toBeInTheDocument()
  })

  it('a stale run is shown with its badge and run age, and its frame is still "drawn" (listed)', () => {
    const timeline = timelineWith({ coverage: [entry({ run_stale: true, run_age_seconds: 46800 })] })
    render(<CoveragePanel timeline={timeline} timelineError={null} selectedMs={selectedMs} />)
    const badge = screen.getByText(/run_stale/)
    expect(badge).toBeInTheDocument()
    expect(badge.textContent).toMatch(/h old/)
  })

  it('run_stale: null shows "run staleness unknown: <reason>"', () => {
    const timeline = timelineWith({ coverage: [entry({ run_stale: null, run_stale_reason: 'cadence not resolvable' })] })
    render(<CoveragePanel timeline={timeline} timelineError={null} selectedMs={selectedMs} />)
    expect(screen.getByText('run staleness unknown: cadence not resolvable')).toBeInTheDocument()
  })

  it('nothing covers this instant reads distinctly, with the notice appended when present', () => {
    const timeline = timelineWith({ coverage: [], coverage_notice: 'nothing covers this instant' })
    render(<CoveragePanel timeline={timeline} timelineError={null} selectedMs={selectedMs} />)
    expect(screen.getByText(/^Nothing covers this instant/)).toBeInTheDocument()
    expect(screen.queryByText(/Coverage unavailable/)).not.toBeInTheDocument()
  })

  it('a failed coverage request reports an error naming the reason, and claims no coverage either way', () => {
    render(<CoveragePanel timeline={null} timelineError="timeline returned 500" selectedMs={selectedMs} />)
    expect(screen.getByText(/^Coverage unavailable: timeline returned 500/)).toBeInTheDocument()
    expect(screen.queryByText(/^Nothing covers this instant/)).not.toBeInTheDocument()
  })

  it('the offset is selected instant minus run time, signed', () => {
    // Run started 30 min before the selected instant.
    const timeline = timelineWith({ coverage: [entry({ run_time: '2026-09-02T14:50:00Z' })] })
    render(<CoveragePanel timeline={timeline} timelineError={null} selectedMs={new Date('2026-09-02T15:20:00Z').getTime()} />)
    expect(screen.getByText(/30 min before the selected instant/)).toBeInTheDocument()
  })
})
