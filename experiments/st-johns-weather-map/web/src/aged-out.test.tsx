import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { normalizePoint, type ApiPointResponse } from './api'
import {
  ABSENCE_LEGEND,
  ABSENCE_STATES,
  absenceBadge,
  resolveAbsenceState,
  stJohnsLocalTime,
} from './fieldFamily'
import { AbsenceStateLegend } from './FieldFamilyPanel'

vi.mock('./MapPanel', () => ({
  MapPanel: ({ label }: { label: string }) => <section aria-label={`${label} map pane`} />,
}))

const response = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })

const point = (fields: unknown[], extra: Record<string, unknown> = {}): ApiPointResponse => ({
  data_mode: 'live',
  valid_time: '2026-09-02T15:00:00Z',
  selection: { mode: 'fallback', badge: 'HRDPS primary', selected_source_id: 'eccc-hrdps', selected_product_id: 'hrdps' },
  fields,
  notices: [],
  ...extra,
} as unknown as ApiPointResponse)

function routedFetch(pointBody: unknown, sources: unknown[] = []) {
  return vi.fn(async (url: string) => {
    if (url.includes('/methods')) return response({ default_method: 'baseline', methods: [], notices: [] })
    if (url.includes('/space-weather')) return response({})
    if (url.includes('/astronomy')) return response({})
    if (url.includes('/sources/status')) return response({ data_mode: 'live', statuses: [] })
    if (url.includes('/point')) return response(pointBody)
    if (url.includes('/layers')) return response({ layers: [] })
    if (url.includes('/catalog')) return response({ data_mode: 'live', sources })
    if (url.includes('/timeline')) return response({ data_mode: 'live', start: '', end: '', items: [] })
    return response({})
  })
}

/** A value that is present, so the family panel has something to render beside
 *  the absences. Without one member carrying a catalogue key the panel refuses
 *  to render at all, which is its own (correct) behaviour and not this test's. */
const hrdpsCloud = {
  field: 'total_cloud_opacity', value: 41, key: 'total_cloud_opacity', family: 'cloud_cover', phase: null, storage: 'stored',
  provenance: {
    source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'percent', data_mode: 'live',
    evidence_class: 'retrieved', delivery_kind: 'published_cell', display_primary_eligible: true,
  },
}

/** The wire shape section 5.1 lands: a field whose valid time has left the
 *  sliding window arrives with no value, `data_mode: "unavailable"`, the
 *  `aged_out` flag, and the last valid time the store recorded for the stream. */
const agedOut = {
  field: 'wind_speed_10m', value: null, key: 'wind_speed_10m', family: 'wind', phase: null, storage: 'stored',
  provenance: {
    source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', data_mode: 'unavailable',
    evidence_class: 'retrieved', display_primary_eligible: true,
    last_valid_time: '2026-09-01T02:30:00Z',
    quality: { status: 'unavailable', flags: ['aged_out'] },
  },
}

const retrievalFailed = {
  field: 'visibility', value: null, key: 'visibility', family: 'visibility', phase: null, storage: 'stored',
  provenance: {
    source_id: 'noaa-gfs', product: 'GFS', provider: 'NOAA', data_mode: 'unavailable',
    evidence_class: 'retrieved', display_primary_eligible: true,
    quality: { status: 'unavailable', flags: ['retrieval_failed'] },
  },
}

describe('aged out is resolved from the wire, not guessed', () => {
  it('reads the state off quality.flags, where the contract puts it', () => {
    // `status` says only "unavailable" for an out-of-window field; the state
    // rides on the flag, so a reader of the status alone would lose it.
    expect(resolveAbsenceState('unavailable', ['aged_out'])).toBe('aged_out')
    expect(resolveAbsenceState('unavailable', ['retrieval_failed'])).toBe('retrieval_failed')
    expect(resolveAbsenceState('unavailable', ['blocked'])).toBe('blocked')
    // A status that names a state directly is still honoured.
    expect(resolveAbsenceState('aged_out')).toBe('aged_out')
    expect(resolveAbsenceState('blocked')).toBe('blocked')
    // Nothing declared is nothing claimed.
    expect(resolveAbsenceState('ok', [])).toBeNull()
    expect(resolveAbsenceState(null)).toBeNull()
    expect(resolveAbsenceState(undefined, ['derived'])).toBeNull()
    // The four quality states, and only these four.
    expect([...ABSENCE_STATES]).toEqual(['null', 'blocked', 'retrieval_failed', 'aged_out'])
  })

  it('lets the most specific flag win, so a rendered state cannot flicker', () => {
    expect(resolveAbsenceState('unavailable', ['null', 'aged_out'])).toBe('aged_out')
    expect(resolveAbsenceState('unavailable', ['aged_out', 'null'])).toBe('aged_out')
  })

  it('normalises last_valid_time, and treats it as optional', () => {
    const withTime = normalizePoint(point([agedOut]))
    expect(withTime.servedFields[0].attribution.lastValidTime).toBe('2026-09-01T02:30:00Z')
    expect(withTime.servedFields[0].attribution.qualityFlags).toContain('aged_out')
    // An API that does not serve it yet leaves it null rather than absent.
    const without = normalizePoint(point([hrdpsCloud]))
    expect(without.servedFields[0].attribution.lastValidTime).toBeNull()
  })
})

describe('the last valid time is read from the zone, in both directions', () => {
  it('renders a summer instant as NDT and a winter one as NST', () => {
    // Newfoundland is UTC-2:30 in summer and UTC-3:30 in winter. Reading the
    // offset from the zone rather than from a constant is what makes both
    // sides of the DST transition right.
    const summer = stJohnsLocalTime('2026-09-01T02:30:00Z')!
    expect(summer).toContain('NDT')
    expect(summer).toContain('00:00')
    const winter = stJohnsLocalTime('2026-01-15T13:00:00Z')!
    expect(winter).toContain('NST')
    expect(winter).toContain('09:30')
  })

  it('refuses to format an absent or unparseable instant', () => {
    expect(stJohnsLocalTime(null)).toBeNull()
    expect(stJohnsLocalTime('')).toBeNull()
    expect(stJohnsLocalTime('not an instant')).toBeNull()
  })
})

describe('five absence states, five different things said', () => {
  it('gives each state its own badge and its own sentence', () => {
    const badges = [
      absenceBadge('stored', 'null', null)!,
      absenceBadge('stored', 'blocked', null)!,
      absenceBadge('stored', 'retrieval_failed', null)!,
      absenceBadge('available-not-stored', null, null)!,
      absenceBadge('stored', 'aged_out', '2026-09-01T02:30:00Z')!,
    ]
    expect(new Set(badges.map((badge) => badge.state)).size).toBe(5)
    expect(new Set(badges.map((badge) => badge.label)).size).toBe(5)
    expect(new Set(badges.map((badge) => badge.sentence)).size).toBe(5)
    // The one a retry may clear says so, and the four that it may not do not.
    expect(badges[2].sentence).toMatch(/later cycle may clear/)
    for (const badge of [badges[0], badges[1], badges[3], badges[4]]) {
      expect(badge.sentence).not.toMatch(/may clear/)
    }
    // A value with something to show has nothing to explain.
    expect(absenceBadge('stored', null, null)).toBeNull()
  })

  it('puts the local time on the aged-out badge and the ISO instant in its text', () => {
    const badge = absenceBadge('stored', 'aged_out', '2026-09-01T02:30:00Z')!
    expect(badge.state).toBe('aged_out')
    expect(badge.label).toMatch(/^Aged out at /)
    expect(badge.label).toContain('NDT')
    expect(badge.sentence).toContain('2026-09-01T02:30:00Z')
    expect(badge.sentence).toContain("St. John's")
  })

  it('will not report aged out without a last valid time', () => {
    // The spec forbids it, and the alternative — falling back to `null` —
    // would say "never retrieved" about a value that was.
    for (const time of [null, '', 'not an instant']) {
      const badge = absenceBadge('stored', 'aged_out', time)!
      expect(badge.state).toBe('unavailable')
      expect(badge.label).toBe('Unavailable')
      expect(badge.sentence).toMatch(/no readable last valid time/)
    }
  })

  it('answers the storage axis before the quality one', () => {
    // A field this deployment never fetches cannot have aged out of a store
    // that never held it, and the upstream fact is the one worth saying.
    expect(absenceBadge('available-not-stored', 'null', null)!.state).toBe('available-not-stored')
    expect(absenceBadge('not-published', 'null', null)!.state).toBe('not-published')
  })
})

describe('the reader can decode every empty slot', () => {
  it('lists all five states in the legend, whether or not any is in view', () => {
    const { container } = render(<AbsenceStateLegend />)
    expect(ABSENCE_LEGEND).toHaveLength(5)
    const states = [...container.querySelectorAll('[data-absence-state]')].map((node) => node.getAttribute('data-absence-state'))
    expect(states).toEqual(['null', 'blocked', 'retrieval_failed', 'available-not-stored', 'aged_out'])
    expect(screen.getByText('Aged out at <last valid time>')).toBeInTheDocument()
    expect(screen.getByText('Retrieval failed')).toBeInTheDocument()
    expect(screen.getByText('Not stored here')).toBeInTheDocument()
    expect(screen.getByText('Blocked')).toBeInTheDocument()
    expect(screen.getByText('No value')).toBeInTheDocument()
  })

  it('shows an aged-out field with its last valid time, apart from a failed retrieval', async () => {
    vi.stubGlobal('fetch', routedFetch(point([hrdpsCloud, agedOut, retrievalFailed])))
    render(<App />)
    const families = await screen.findByLabelText('Readings by field family')

    const aged = within(families).getByText('wind_speed_10m').closest('li') as HTMLElement
    const agedBadge = aged.querySelector('[data-absence-state="aged_out"]')!
    expect(agedBadge.textContent).toMatch(/^Aged out at /)
    expect(agedBadge.textContent).toContain('NDT')
    // The unambiguous form travels in the text alternative beside the badge.
    const agedLine = aged.querySelector('.family-member-absence')!
    expect(agedLine.textContent).toContain('2026-09-01T02:30:00Z')
    expect(agedLine.textContent).toContain('left the retention window')
    // And no number is invented where the frame used to be.
    expect(within(aged).queryByText(/^\d/)).not.toBeInTheDocument()

    const failed = within(families).getByText('visibility').closest('li') as HTMLElement
    const failedBadge = failed.querySelector('[data-absence-state="retrieval_failed"]')!
    expect(failedBadge.textContent).toBe('Retrieval failed')
    // The two are never the same claim: one is a retention edge, one is a
    // broken attempt, and only the second suggests waiting for another cycle.
    expect(failedBadge.textContent).not.toBe(agedBadge.textContent)
    expect(failed.querySelector('.family-member-absence')!.textContent).toMatch(/later cycle may clear/)
  })

  it('shows an aged-out claim with no last valid time as unavailable, never as never-retrieved', async () => {
    const noTime = { ...agedOut, provenance: { ...agedOut.provenance, last_valid_time: null } }
    vi.stubGlobal('fetch', routedFetch(point([hrdpsCloud, noTime])))
    render(<App />)
    const families = await screen.findByLabelText('Readings by field family')
    const row = within(families).getByText('wind_speed_10m').closest('li') as HTMLElement
    // Every state this row claims, read off the badges themselves. Enumerated
    // rather than probed one selector at a time: jsdom's selector engine
    // answers `[data-absence-state="null"]` with elements carrying no such
    // attribute at all, so a probe for the state named "null" is not a
    // question this environment can be asked.
    const states = [...row.querySelectorAll('[data-absence-state]')].map((node) => node.getAttribute('data-absence-state'))
    expect(states).toContain('unavailable')
    expect(states).not.toContain('aged_out')
    expect(states).not.toContain('null')
    expect(row.textContent).toContain('no readable last valid time')
  })
})
