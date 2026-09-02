import { render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { noticeForField, nonPrimarySourceIds, normalizePoint, type ApiPointResponse } from './api'
import { deliveryKindLabel, resolveDeliveryKind } from './deliveryKind'
import type { CatalogSource } from './types'

vi.mock('./MapPanel', () => ({
  MapPanel: ({ label }: { label: string }) => <section aria-label={`${label} map pane`} />,
}))

const response = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })

const point = (fields: unknown[], notices: string[] = []): ApiPointResponse => ({
  data_mode: 'live',
  valid_time: '2026-09-02T15:00:00Z',
  selection: { mode: 'fallback', badge: 'HRDPS primary', selected_source_id: 'eccc-hrdps', selected_product_id: 'hrdps' },
  fields,
  notices,
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

const temperature = {
  field: 'temperature', value: 12.4,
  provenance: {
    source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'degC', data_mode: 'live',
    evidence_class: 'retrieved', delivery_kind: 'published_cell', display_primary_eligible: true,
  },
}

describe('the delivery kind is a second axis, and it is labelled', () => {
  it('reads only the three declared kinds, and nothing else', () => {
    expect(resolveDeliveryKind('published_cell')).toBe('published_cell')
    expect(resolveDeliveryKind('reprocessed')).toBe('reprocessed')
    expect(resolveDeliveryKind('intermediary_derived')).toBe('intermediary_derived')
    for (const value of ['retrieved', 'derived_here', '', undefined, null, 4]) {
      expect(resolveDeliveryKind(value)).toBeNull()
    }
  })

  it('says how each kind reached this deployment', () => {
    expect(deliveryKindLabel('published_cell', null)).toBe("producer's own cell")
    expect(deliveryKindLabel('reprocessed', 'Open-Meteo')).toBe('reprocessed by Open-Meteo')
    expect(deliveryKindLabel('intermediary_derived', 'Open-Meteo')).toBe('computed by Open-Meteo')
  })

  it('renders no label at all when the record declared no kind', () => {
    // The kind is a registry attribute. Its absence is a gap in the registry,
    // not an evidence failure, so it must not read as a doubt about a value
    // the way an absent evidence class does.
    expect(deliveryKindLabel(null, null)).toBeNull()
    expect(deliveryKindLabel(null, 'Open-Meteo')).toBeNull()
  })

  it('names an unnamed intermediary rather than reading as the producer’s own', () => {
    expect(deliveryKindLabel('reprocessed', null)).toBe('reprocessed by an unnamed intermediary')
    expect(deliveryKindLabel('intermediary_derived', null)).toBe('computed by an unnamed intermediary')
  })

  it('renders the label beside the class badge on a value', async () => {
    vi.stubGlobal('fetch', routedFetch(point([temperature])))
    render(<App />)
    await waitFor(() => expect(screen.getAllByText("producer's own cell").length).toBeGreaterThan(0))
    expect(screen.getAllByText("producer's own cell")[0]).toHaveAttribute('data-delivery-kind', 'published_cell')
  })

  it('shows no delivery label for a value whose provenance declared no kind', async () => {
    const undeclared = { ...temperature, provenance: { ...temperature.provenance, delivery_kind: undefined } }
    vi.stubGlobal('fetch', routedFetch(point([undeclared])))
    render(<App />)
    await waitFor(() => expect(screen.getAllByText('retrieved').length).toBeGreaterThan(0))
    expect(screen.queryByText("producer's own cell")).not.toBeInTheDocument()
    expect(document.querySelector('[data-delivery-kind]')).toBeNull()
  })

  it('shows the kind in the source catalogue view', async () => {
    const sources: CatalogSource[] = [{
      id: 'eccc-hrdps', producer: 'ECCC', product: 'HRDPS', state: 'implementing', status_reason: 'implementing',
      role: 'Regional guidance', may_enter_consensus: false, cadence: '6 h', forecast_horizon: '48 h',
      geographic_coverage: 'Atlantic', licence: 'OGL', attribution: 'ECCC',
      delivery_kind: 'published_cell', intermediary: null, display_primary: true,
    }]
    vi.stubGlobal('fetch', routedFetch(point([temperature]), sources))
    render(<App />)
    const button = await screen.findByRole('button', { name: /HRDPS/ })
    expect(within(button).getByText("producer's own cell")).toHaveAttribute('data-delivery-kind', 'published_cell')
  })
})

describe('a value that may not be the primary is only ever an alternative', () => {
  it('collects the catalogue records the registry refuses as primaries', () => {
    const source = (id: string, displayPrimary?: boolean): CatalogSource => ({
      id, producer: 'p', product: 'q', state: 's', status_reason: '', role: '', may_enter_consensus: false,
      cadence: '', forecast_horizon: '', geographic_coverage: '', licence: '', attribution: '',
      ...(displayPrimary === undefined ? {} : { display_primary: displayPrimary }),
    })
    const refused = nonPrimarySourceIds([source('a', false), source('b', true), source('c')])
    expect([...refused]).toEqual(['a'])
    // Absent is NOT false: an undeclared record is undeclared, not refused,
    // and blanking its reading would punish a gap in the registry.
    expect(refused.has('c')).toBe(false)
  })

  it('keeps a reprocessed value out of the reading even when it is the only value', () => {
    const snapshot = normalizePoint(point([{
      field: 'visibility', value: 9000,
      provenance: {
        source_id: 'open-meteo', product: 'IFS via Open-Meteo', provider: 'ECMWF', normalized_units: 'm',
        data_mode: 'live', evidence_class: 'reprocessed', delivery_kind: 'reprocessed', intermediary: 'Open-Meteo',
        display_primary_eligible: false,
      },
    }]))
    expect(snapshot.visibilityKm).toBeNull()
    expect(snapshot.fieldAlternatives.visibility).toHaveLength(1)
    expect(snapshot.fieldAlternatives.visibility[0].attribution.deliveryKind).toBe('reprocessed')
    expect(snapshot.fieldAlternatives.visibility[0].text).toBe('9000 m')
  })

  it('keeps it out even when the response selected its source', () => {
    // The selection names the source; the class still refuses it the slot.
    const snapshot = normalizePoint(point([{
      field: 'temperature', value: 18,
      provenance: {
        source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'degC', data_mode: 'live',
        evidence_class: 'uncalibrated_observation', display_primary_eligible: false,
      },
    }]))
    expect(snapshot.temperatureC).toBeNull()
    expect(snapshot.fieldAlternatives.temperature[0].attribution.evidenceClass).toBe('uncalibrated_observation')
  })

  it('prefers a retrieved value over a reprocessed one for the same field', () => {
    const snapshot = normalizePoint(point([
      { field: 'temperature', value: 9, provenance: { source_id: 'open-meteo', product: 'IFS via Open-Meteo', provider: 'ECMWF', normalized_units: 'degC', data_mode: 'live', evidence_class: 'reprocessed', delivery_kind: 'reprocessed', intermediary: 'Open-Meteo', display_primary_eligible: false } },
      { field: 'temperature', value: 12.4, provenance: { source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'degC', data_mode: 'live', evidence_class: 'retrieved', delivery_kind: 'published_cell', display_primary_eligible: true } },
    ]))
    // The reprocessed value is listed FIRST in the response; first-match must
    // not win over the producer's own cell.
    expect(snapshot.temperatureC).toBe(12.4)
    expect(snapshot.fieldSources.temperature.sourceId).toBe('eccc-hrdps')
    expect(snapshot.fieldAlternatives.temperature[0].attribution.sourceId).toBe('open-meteo')
  })

  it('refuses a source the catalogue marks display_primary false, whatever its class', () => {
    const field = [{
      field: 'temperature', value: 12.4,
      provenance: {
        source_id: 'some-aggregator', product: 'X', provider: 'Y', normalized_units: 'degC', data_mode: 'live',
        evidence_class: 'retrieved', delivery_kind: 'published_cell', display_primary_eligible: true,
      },
    }]
    // Its own provenance says it may be a primary; the registry says otherwise.
    expect(normalizePoint(point(field)).temperatureC).toBe(12.4)
    const refused = normalizePoint(point(field), { nonPrimarySources: new Set(['some-aggregator']) })
    expect(refused.temperatureC).toBeNull()
    expect(refused.fieldAlternatives.temperature).toHaveLength(1)
  })

  it('renders the alternative with its badge and label, outside the metric', async () => {
    vi.stubGlobal('fetch', routedFetch(point([
      temperature,
      {
        field: 'total_cloud', value: 44,
        provenance: {
          source_id: 'open-meteo-weathernext-2', product: 'WeatherNext 2 via Open-Meteo', provider: 'Google DeepMind',
          normalized_units: 'percent', data_mode: 'live', evidence_class: 'intermediary_derived',
          delivery_kind: 'intermediary_derived', intermediary: 'Open-Meteo',
          intermediary_method: 'cloud cover from the humidity profile', display_primary_eligible: false,
        },
      },
    ])))
    render(<App />)
    const alternatives = await screen.findByLabelText('Alternative readings')
    expect(within(alternatives).getByText('44 percent')).toBeInTheDocument()
    expect(within(alternatives).getByText('intermediary derived')).toHaveAttribute('data-evidence-class', 'intermediary_derived')
    expect(within(alternatives).getByText('computed by Open-Meteo')).toBeInTheDocument()
    expect(within(alternatives).getByText(/Method: cloud cover from the humidity profile/)).toBeInTheDocument()
    // The metric itself shows no number for it.
    const metric = screen.getByText('Total cloud').closest('.metric') as HTMLElement
    expect(within(metric).queryByText('44%')).not.toBeInTheDocument()
  })

  it('says the transformation is undocumented rather than implying there was none', async () => {
    vi.stubGlobal('fetch', routedFetch(point([
      temperature,
      {
        field: 'total_cloud', value: 44,
        provenance: {
          source_id: 'open-meteo', product: 'X via Open-Meteo', provider: 'Producer', normalized_units: 'percent',
          data_mode: 'live', evidence_class: 'reprocessed', delivery_kind: 'reprocessed', intermediary: 'Open-Meteo',
          display_primary_eligible: false,
        },
      },
    ])))
    render(<App />)
    const alternatives = await screen.findByLabelText('Alternative readings')
    expect(within(alternatives).getByText(/documents no method for this field, so the transformation is undocumented rather than absent/)).toBeInTheDocument()
  })
})

describe('a refused derivation and an unmodelled artifact read as unavailable', () => {
  const refusedNotice = 'artifact from eccc-hrdps (revision r1) was skipped: relative_humidity was not derived because the relative_humidity_from_dew_point entry is disabled; nothing was substituted'

  it('matches the response notice to the field it names', () => {
    const snapshot = normalizePoint(point([
      temperature,
      {
        field: 'relative_humidity', value: null,
        provenance: {
          source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'percent', data_mode: 'live',
          evidence_class: 'derived_here', quality: { status: 'unknown', flags: ['derivation_refused'] },
        },
      },
    ], [refusedNotice]))
    const humidity = snapshot.fieldSources.relative_humidity
    expect(humidity.derivationRefused).toBe(true)
    expect(humidity.notice).toBe(refusedNotice)
    expect(snapshot.notices).toEqual([refusedNotice])
  })

  it('falls back to a notice naming the source when none names the field', () => {
    const attribution = normalizePoint(point([{
      field: 'temperature', value: null,
      provenance: {
        source_id: 'noaa-gfs', product: 'GFS', provider: 'NOAA', normalized_units: 'degC', data_mode: 'live',
        evidence_class: 'retrieved', quality: { status: 'unknown', flags: ['provenance_unmodelled'] },
      },
    }], ['artifact from noaa-gfs (revision r9) was skipped: provenance could not be modelled'])).fieldSources.temperature
    expect(attribution.provenanceUnmodelled).toBe(true)
    expect(attribution.notice).toContain('noaa-gfs')
  })

  it('matches no notice for a value that is a reading rather than a refusal', () => {
    const snapshot = normalizePoint(point([temperature], [refusedNotice]))
    expect(snapshot.fieldSources.temperature.notice).toBeNull()
    expect(noticeForField('temperature', snapshot.fieldSources.temperature, [refusedNotice])).toBeNull()
  })

  it('renders a refused derivation as unavailable with the notice beside it', async () => {
    vi.stubGlobal('fetch', routedFetch(point([
      temperature,
      {
        field: 'relative_humidity', value: null,
        provenance: {
          source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'percent', data_mode: 'live',
          evidence_class: 'derived_here', quality: { status: 'unknown', flags: ['derivation_refused'] },
        },
      },
    ], [refusedNotice])))
    render(<App />)
    const humidity = await waitFor(() => screen.getByText('Humidity').closest('.metric') as HTMLElement)
    await waitFor(() => expect(within(humidity).getByText('Unavailable')).toBeInTheDocument())
    expect(within(humidity).getByText(/the relative_humidity_from_dew_point entry is disabled/)).toBeInTheDocument()
  })

  it('renders an unmodelled artifact as unavailable with its notice', async () => {
    const notice = 'artifact from eccc-hrdps (revision r4) was skipped: provenance could not be modelled: evidence_class missing'
    vi.stubGlobal('fetch', routedFetch(point([{
      field: 'temperature', value: null,
      provenance: {
        source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'degC', data_mode: 'live',
        evidence_class: 'retrieved', quality: { status: 'unknown', flags: ['provenance_unmodelled'] },
      },
    }], [notice])))
    render(<App />)
    await waitFor(() => expect(screen.getByText(/provenance could not be modelled/)).toBeInTheDocument())
  })

  it('says the response gave no reason rather than inventing one', async () => {
    vi.stubGlobal('fetch', routedFetch(point([
      temperature,
      {
        field: 'relative_humidity', value: null,
        provenance: {
          source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'percent', data_mode: 'live',
          evidence_class: 'derived_here', quality: { status: 'unknown', flags: ['derivation_refused'] },
        },
      },
    ], [])))
    render(<App />)
    const humidity = await waitFor(() => screen.getByText('Humidity').closest('.metric') as HTMLElement)
    expect(within(humidity).getByText('the derivation was refused and the response gave no reason')).toBeInTheDocument()
  })
})
