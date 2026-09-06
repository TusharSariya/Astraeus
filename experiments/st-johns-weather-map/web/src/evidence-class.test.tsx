import { render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { layerEvidenceClass, normalizePoint, type ApiPointResponse } from './api'
import { EVIDENCE_CLASSES, describeEvidenceClassSentence, resolveEvidenceClass } from './evidenceClass'
import type { LayerItem } from './types'

// The map is stubbed the way App.test.tsx stubs it: this suite is about the
// readings panel and the pure layer logic, and the drawer's rendered badge is
// asserted in MapPanel.test.tsx where the MapLibre fake already lives.
vi.mock('./MapPanel', () => ({
  MapPanel: ({ label }: { label: string }) => <section aria-label={`${label} map pane`} />,
}))

const point = (fields: unknown[], selection: Record<string, unknown> = { mode: 'fallback', badge: 'HRDPS primary', selected_source_id: 'eccc-hrdps', selected_product_id: 'hrdps' }): ApiPointResponse => ({
  data_mode: 'live',
  valid_time: '2026-09-02T15:00:00Z',
  selection,
  fields,
} as unknown as ApiPointResponse)

const response = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })

function routedFetch(pointBody: unknown) {
  return vi.fn(async (url: string) => {
    if (url.includes('/methods')) return response({ default_method: 'baseline', methods: [], notices: [] })
    if (url.includes('/space-weather')) return response({})
    if (url.includes('/astronomy')) return response({})
    if (url.includes('/sources/status')) return response({ data_mode: 'live', statuses: [] })
    if (url.includes('/point')) return response(pointBody)
    if (url.includes('/layers')) return response({ layers: [] })
    if (url.includes('/catalog')) return response({ sources: [] })
    if (url.includes('/timeline')) return response({ data_mode: 'live', start: '', end: '', items: [] })
    return response({})
  })
}

const hrdps = (extra: Record<string, unknown>) => ({
  source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'Environment and Climate Change Canada',
  normalized_units: 'degC', data_mode: 'live', ...extra,
})

describe('the six evidence classes are the client’s whole vocabulary', () => {
  it('resolves each of the six declared classes to itself', () => {
    for (const evidenceClass of EVIDENCE_CLASSES) {
      expect(resolveEvidenceClass(evidenceClass)).toBe(evidenceClass)
    }
    expect(EVIDENCE_CLASSES).toHaveLength(6)
  })

  it('resolves an unknown name, an absent field and a non-string to unrecognised, never to retrieved', () => {
    // The failure this guards is the one the class field exists to prevent: a
    // value of unstated origin quietly acquiring the strongest claim.
    for (const declared of ['consensus', 'blend', 'derived', '', undefined, null, 7, {}]) {
      expect(resolveEvidenceClass(declared)).toBe('unrecognised')
    }
  })

  it('carries the class from provenance onto the field attribution', () => {
    const snapshot = normalizePoint(point([
      { field: 'temperature', value: 12, provenance: hrdps({ evidence_class: 'retrieved' }) },
      { field: 'total_cloud', value: 44, provenance: hrdps({ evidence_class: 'intermediary_derived', normalized_units: 'percent' }) },
    ]))
    expect(snapshot.fieldSources.temperature.evidenceClass).toBe('retrieved')
    expect(snapshot.fieldSources.temperature.declaredClass).toBe('retrieved')
    // The intermediary-derived value is never the reading, so it is not in
    // `fieldSources` at all — it is an alternative, and carries its class there.
    expect(snapshot.fieldSources.total_cloud).toBeUndefined()
    expect(snapshot.totalCloudPct).toBeNull()
    expect(snapshot.fieldAlternatives.total_cloud[0].attribution.evidenceClass).toBe('intermediary_derived')
  })

  it('records every class a provider/product row reported, deduplicated', () => {
    const snapshot = normalizePoint(point([
      { field: 'temperature', value: 12, provenance: hrdps({ evidence_class: 'retrieved' }) },
      { field: 'dew_point', value: 9, provenance: hrdps({ evidence_class: 'retrieved' }) },
      { field: 'relative_humidity', value: 80, provenance: hrdps({ evidence_class: 'derived_here', normalized_units: 'percent' }) },
    ]))
    const row = snapshot.provenance.find((entry) => entry.product === 'HRDPS')
    expect(row?.evidenceClasses).toEqual(['retrieved', 'derived_here'])
  })
})

describe('every value shows its class', () => {
  it('badges a retrieved value rather than leaving an empty space', async () => {
    vi.stubGlobal('fetch', routedFetch(point([
      { field: 'temperature', value: 12.4, provenance: hrdps({ evidence_class: 'retrieved' }) },
      { field: 'dew_point', value: 9.1, provenance: hrdps({ evidence_class: 'retrieved' }) },
    ])))
    render(<App />)
    const dewPoint = await waitFor(() => screen.getByText('Dew point').closest('.metric') as HTMLElement)
    await waitFor(() => expect(within(dewPoint).getByText('9.1°C')).toBeInTheDocument())
    const badge = within(dewPoint).getByText('retrieved')
    expect(badge).toHaveAttribute('data-evidence-class', 'retrieved')
    // The headline number carries one too: the badge is not an expert-only tag.
    expect(screen.getAllByText('retrieved').length).toBeGreaterThan(1)
  })

  it('badges a reprocessed value with its own class, beside the reading rather than in it', async () => {
    vi.stubGlobal('fetch', routedFetch(point([
      { field: 'temperature', value: 12.4, provenance: hrdps({ evidence_class: 'retrieved' }) },
      { field: 'visibility', value: 9000, provenance: hrdps({ evidence_class: 'reprocessed', normalized_units: 'm', delivery_kind: 'reprocessed', intermediary: 'Open-Meteo' }) },
    ])))
    render(<App />)
    // The reprocessed value may not be the reading, so the metric is Unknown...
    const visibility = await waitFor(() => screen.getByText('Visibility').closest('.metric') as HTMLElement)
    await waitFor(() => expect(within(visibility).getByText('Unknown')).toBeInTheDocument())
    expect(within(visibility).queryByText('9.0 km')).not.toBeInTheDocument()
    // ...and it is shown as an alternative, with its own class and its label.
    const alternatives = screen.getByLabelText('Alternative readings')
    expect(within(alternatives).getByText('reprocessed')).toHaveAttribute('data-evidence-class', 'reprocessed')
    expect(within(alternatives).getByText('reprocessed by Open-Meteo')).toBeInTheDocument()
    expect(within(alternatives).getByText('9000 m')).toBeInTheDocument()
  })
})

describe('an unrecognised class is unavailable with its reason', () => {
  it('shows no number for a class the client does not know, and names it', async () => {
    vi.stubGlobal('fetch', routedFetch(point([
      { field: 'temperature', value: 12.4, provenance: hrdps({ evidence_class: 'retrieved' }) },
      { field: 'dew_point', value: 9.1, provenance: hrdps({ evidence_class: 'consensus_blend' }) },
    ])))
    render(<App />)
    const dewPoint = await waitFor(() => screen.getByText('Dew point').closest('.metric') as HTMLElement)
    await waitFor(() => expect(within(dewPoint).getByText('Unavailable')).toBeInTheDocument())
    expect(within(dewPoint).queryByText('9.1°C')).not.toBeInTheDocument()
    expect(within(dewPoint).getByText(/unrecognised evidence class “consensus_blend”/)).toBeInTheDocument()
    expect(within(dewPoint).queryByText('retrieved')).not.toBeInTheDocument()
  })

  it('treats a value whose provenance declared no class the same way', async () => {
    vi.stubGlobal('fetch', routedFetch(point([
      { field: 'temperature', value: 12.4, provenance: hrdps({ evidence_class: 'retrieved' }) },
      { field: 'dew_point', value: 9.1, provenance: hrdps({}) },
    ])))
    render(<App />)
    const dewPoint = await waitFor(() => screen.getByText('Dew point').closest('.metric') as HTMLElement)
    await waitFor(() => expect(within(dewPoint).getByText('Unavailable')).toBeInTheDocument())
    expect(within(dewPoint).getByText(/unrecognised evidence class — the response declared none/)).toBeInTheDocument()
  })

  it('suppresses the headline temperature too when its class is unrecognised', async () => {
    vi.stubGlobal('fetch', routedFetch(point([
      { field: 'temperature', value: 12.4, provenance: hrdps({ evidence_class: 'not_a_class' }) },
    ])))
    render(<App />)
    await waitFor(() => expect(screen.getByText(/unrecognised evidence class “not_a_class”/)).toBeInTheDocument())
    expect(screen.queryByText('12.4')).not.toBeInTheDocument()
  })
})

describe('the legend names all six classes', () => {
  it('lists every class plus the unrecognised state, so an absent badge is never meaningful', async () => {
    vi.stubGlobal('fetch', routedFetch(point([
      { field: 'temperature', value: 12.4, provenance: hrdps({ evidence_class: 'retrieved' }) },
    ])))
    render(<App />)
    const legend = await waitFor(() => screen.getByText('Evidence class legend').closest('details') as HTMLElement)
    for (const label of ['retrieved', 'reprocessed', 'derived here', 'intermediary derived', 'generated display', 'uncalibrated observation', 'unrecognised evidence class']) {
      expect(within(legend).getAllByText(label).length).toBeGreaterThan(0)
    }
  })
})

describe('every layer shows its class', () => {
  const layer = (extra: Partial<LayerItem>): LayerItem => ({
    id: 'hrdps-cloud', title: 'HRDPS total cloud', kind: 'raster', field: 'total_cloud',
    product: 'HRDPS', units: 'percent', semantics: 'Total cloud cover',
    times: ['2026-09-02T15:00:00Z'], staleness_tolerance_seconds: 3600,
    evidence_basis: 'published_artifact', group: 'rendered_grid',
    raster_available: false, legend_available: false, ...extra,
  })

  it('resolves a layer’s declared class, and an absent one to unrecognised', () => {
    expect(layerEvidenceClass(layer({ evidence_class: 'derived_here' }))).toBe('derived_here')
    expect(layerEvidenceClass(layer({ evidence_class: 'nonsense' }))).toBe('unrecognised')
    // A published artifact is NOT evidence of a class: the basis says how the
    // value was handled, the class says how it came to exist.
    expect(layerEvidenceClass(layer({}))).toBe('unrecognised')
  })

  it('states the class as a sentence for the text alternative', () => {
    // The badge and this sentence are the same claim: a reader without sight
    // of the drawer must not get a weaker one.
    expect(describeEvidenceClassSentence(layer({ evidence_class: 'generated_display' })))
      .toContain('Evidence class generated display')
    expect(describeEvidenceClassSentence(layer({})))
      .toContain('Evidence class unavailable: unrecognised evidence class — the response declared none')
  })
})
