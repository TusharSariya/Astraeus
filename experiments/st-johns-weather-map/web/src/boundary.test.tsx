import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TimelineDock, type TimelineDockProps } from './TimelineDock'
import {
  boundaryMark, FALLBACK_BACK_MINUTES, FALLBACK_FORWARD_MINUTES, HORIZON_SCALE_MARKS, planningTierHasCoverage, windowFromTimeline,
} from './tierBoundary'
import { placeScaleMarks, textMeasurer } from './scrubberAxis'
import type { TimelineItem, TimelineResponse } from './types'

vi.mock('./MethodMenu', () => ({ MethodMenu: () => null }))

const measure = (text: string) => text.length * 6

describe('windowFromTimeline: the window the scrubber spans (task 4.1)', () => {
  const reference = new Date('2026-09-02T12:00:00Z')

  it('falls back to 24 h back / 14 d ahead when there is no timeline', () => {
    expect(windowFromTimeline(null, reference)).toEqual({ backMinutes: FALLBACK_BACK_MINUTES, forwardMinutes: FALLBACK_FORWARD_MINUTES })
    expect(FALLBACK_BACK_MINUTES).toBe(24 * 60)
    expect(FALLBACK_FORWARD_MINUTES).toBe(14 * 24 * 60)
  })

  it('falls back when the declared bounds do not parse', () => {
    expect(windowFromTimeline({ start: '', end: '' }, reference)).toEqual({ backMinutes: FALLBACK_BACK_MINUTES, forwardMinutes: FALLBACK_FORWARD_MINUTES })
  })

  it('reads the window from /timeline start..end when it is available', () => {
    const bounds = windowFromTimeline({ start: '2026-09-01T12:00:00Z', end: '2026-09-16T12:00:00Z' }, reference)
    expect(bounds).toEqual({ backMinutes: 24 * 60, forwardMinutes: 14 * 24 * 60 })
  })
})

describe('boundaryMark: the 24 h boundary is a marked position, not colour alone', () => {
  const windowStartMs = new Date('2026-09-01T12:00:00Z').getTime()
  const windowEndMs = new Date('2026-09-16T12:00:00Z').getTime()
  const boundaryIso = '2026-09-02T12:00:00Z'
  const tiers = [
    { id: 'core', start: '2026-09-01T12:00:00Z', end: boundaryIso },
    { id: 'planning', start: boundaryIso, end: '2026-09-16T12:00:00Z' },
  ]

  it('is null when the API declared no boundary — never a guessed one', () => {
    expect(boundaryMark(null, tiers, windowStartMs, windowEndMs)).toBeNull()
    expect(boundaryMark(undefined, tiers, windowStartMs, windowEndMs)).toBeNull()
  })

  it('is null when the boundary instant does not parse', () => {
    expect(boundaryMark('not an instant', tiers, windowStartMs, windowEndMs)).toBeNull()
  })

  it('places the mark at its fraction of the window and carries a tick-plus-label plus a text alternative naming both ranges', () => {
    const mark = boundaryMark(boundaryIso, tiers, windowStartMs, windowEndMs)!
    expect(mark.fraction).toBeCloseTo(1 / 15, 5) // 24h into a 15-day window
    expect(mark.label).not.toMatch(/^#/) // a real label, not a colour token
    expect(mark.label.length).toBeGreaterThan(0)
    expect(mark.description).toContain('2026-09-01T12:00:00Z')
    expect(mark.description).toContain(boundaryIso)
    expect(mark.description).toContain('2026-09-16T12:00:00Z')
  })

  it('describes the generic tier ranges when the API declared no tiers', () => {
    const mark = boundaryMark(boundaryIso, null, windowStartMs, windowEndMs)!
    expect(mark.description).toMatch(/24 h back to 24 h ahead/)
    expect(mark.description).toMatch(/24 h ahead to 14 d ahead/)
  })
})

describe('planningTierHasCoverage: the no-frames-beyond-boundary case', () => {
  const boundary = '2026-09-02T12:00:00Z'

  function item(hourIso: string, coverage: unknown[] | undefined): TimelineItem {
    return { valid_time_utc: hourIso, valid_time_newfoundland: hourIso, available_products: [], coverage: coverage as never }
  }

  it('is true (no note) when boundary itself is unknown', () => {
    expect(planningTierHasCoverage([], null)).toBe(true)
  })

  it('is false when every item past the boundary has empty coverage', () => {
    const items = [item('2026-09-02T13:00:00Z', []), item('2026-09-02T14:00:00Z', [])]
    expect(planningTierHasCoverage(items, boundary)).toBe(false)
  })

  it('is false when nothing at all is published past the boundary', () => {
    const items = [item('2026-09-02T11:00:00Z', [{ source_id: 'x' }])] // before the boundary only
    expect(planningTierHasCoverage(items, boundary)).toBe(false)
  })

  it('is true when at least one item past the boundary has non-empty coverage', () => {
    const items = [item('2026-09-02T13:00:00Z', []), item('2026-09-02T14:00:00Z', [{ source_id: 'noaa-gfs' }])]
    expect(planningTierHasCoverage(items, boundary)).toBe(true)
  })

  it('falls back to available_products on an older API with no coverage array', () => {
    const older: TimelineItem = { valid_time_utc: '2026-09-02T14:00:00Z', valid_time_newfoundland: '', available_products: ['GFS'] }
    expect(planningTierHasCoverage([older], boundary)).toBe(true)
    const olderEmpty: TimelineItem = { valid_time_utc: '2026-09-02T14:00:00Z', valid_time_newfoundland: '', available_products: [] }
    expect(planningTierHasCoverage([olderEmpty], boundary)).toBe(false)
  })
})

describe('HORIZON_SCALE_MARKS: hourly-ish inside the core tier, daily beyond it', () => {
  it('names the step change the spec asks to see', () => {
    const hours = HORIZON_SCALE_MARKS.map((mark) => mark.hours)
    expect(hours).toEqual([-24, -12, 0, 6, 12, 24, 48, 96, 168, 240, 336])
  })

  it('still never overlaps on a narrow or wide rail — placeScaleMarks keeps its collision handling', () => {
    for (const railPx of [700, 900, 1400]) {
      const placed = placeScaleMarks({
        marks: HORIZON_SCALE_MARKS, backMinutes: FALLBACK_BACK_MINUTES, forwardMinutes: FALLBACK_FORWARD_MINUTES, railPx, measure,
      })
      const boxes = placed.map((mark) => {
        const x = mark.fraction * railPx
        const width = measure(mark.text)
        return mark.anchor === 'start' ? [x, x + width] : mark.anchor === 'end' ? [x - width, x] : [x - width / 2, x + width / 2]
      })
      for (let i = 0; i < boxes.length; i += 1) {
        for (let j = i + 1; j < boxes.length; j += 1) {
          const overlap = boxes[i][0] < boxes[j][1] && boxes[j][0] < boxes[i][1]
          expect(overlap).toBe(false)
        }
      }
      // Now, the boundary and the far end always survive.
      expect(placed.map((mark) => mark.hours)).toEqual(expect.arrayContaining([0, 336]))
    }
  })
})

describe('TimelineDock renders the boundary and the no-coverage note', () => {
  function baseProps(overrides: Partial<TimelineDockProps> = {}): TimelineDockProps {
    return {
      offsetMinutes: 0, scrubOffset: '+0h', validClock: '09:00', backMinutes: 24 * 60, forwardMinutes: 14 * 24 * 60,
      snapping: false, ariaValueText: 'Now',
      onScrubMinutes: () => {}, onScrubKeyDown: () => {}, onQuickJump: () => {},
      windowStartMs: new Date('2026-09-01T12:00:00Z').getTime(), windowEndMs: new Date('2026-09-16T12:00:00Z').getTime(),
      markers: { markers: [], axisless: [] }, onJumpToInstant: () => {},
      playing: false, speed: 1, direction: 1, onTogglePlay: () => {}, onFaster: () => {}, onSlower: () => {}, onToggleDirection: () => {},
      interpolate: false, onToggleInterpolate: () => {},
      methods: [], method: 'baseline', onSelectMethod: () => {}, methodNotices: [], methodError: null,
      storyOpen: false, onToggleStory: () => {}, storyToggleRef: { current: null },
      timeline: null, timelineError: null, selectedMs: new Date('2026-09-02T09:00:00Z').getTime(),
      ...overrides,
    }
  }

  it('marks the boundary with a tick, a label and a text alternative naming both tier ranges', () => {
    const timeline: TimelineResponse = {
      data_mode: 'live', start: '2026-09-01T12:00:00Z', end: '2026-09-16T12:00:00Z', items: [],
      boundary: '2026-09-02T12:00:00Z',
      tiers: [
        { id: 'core', start: '2026-09-01T12:00:00Z', end: '2026-09-02T12:00:00Z' },
        { id: 'planning', start: '2026-09-02T12:00:00Z', end: '2026-09-16T12:00:00Z' },
      ],
    }
    render(<TimelineDock {...baseProps({ timeline })} />)
    const dock = screen.getByLabelText('Scrub timeline')
    expect(within(dock).getByText('+24h | planning')).toBeInTheDocument()
    const description = dock.querySelector('#tier-boundary-description')!
    expect(description).toHaveTextContent(/core tier/i)
    expect(description).toHaveTextContent(/planning tier/i)
  })

  it('says the planning tier holds no published frames rather than implying coverage', () => {
    const timeline: TimelineResponse = {
      data_mode: 'live', start: '2026-09-01T12:00:00Z', end: '2026-09-16T12:00:00Z',
      boundary: '2026-09-02T12:00:00Z',
      items: [
        { valid_time_utc: '2026-09-02T13:00:00Z', valid_time_newfoundland: '', available_products: [], coverage: [] },
      ],
    }
    render(<TimelineDock {...baseProps({ timeline })} />)
    expect(screen.getByText('planning tier holds no published frames')).toBeInTheDocument()
  })

  it('draws no boundary tick and no empty-planning note when the timeline is unavailable', () => {
    render(<TimelineDock {...baseProps({ timeline: null })} />)
    expect(screen.queryByText('+24h | planning')).not.toBeInTheDocument()
    expect(screen.queryByText('planning tier holds no published frames')).not.toBeInTheDocument()
  })
})
