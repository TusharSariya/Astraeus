import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { groupLayersByFamily, layerFamily, layerFieldKey, normalizePoint, parseComparability, type ApiPointResponse } from './api'
import {
  UNGROUPED_FAMILY,
  buildComparabilityIndex,
  comparabilityVerdict,
  differenceRefusal,
  familyNote,
  familyTitle,
  fieldDefinition,
  groupByFamily,
  layerComparability,
  resolveFamily,
  resolveStorage,
  unavailableSentence,
} from './fieldFamily'
import { ActiveFamilyLegends, describeLayerFamilySentence } from './MapFamilyLegend'
import type { CatalogSource, LayerItem } from './types'

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

/** The response shape section 3 writes: every value carries `key`, `family`,
 *  `phase` and `storage`, and `/point` carries a `comparability` list. */
const hrdpsCloud = {
  field: 'total_cloud', value: 41, key: 'total_cloud_opacity', family: 'cloud_cover', phase: null, storage: 'stored',
  provenance: {
    source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'percent', data_mode: 'live',
    evidence_class: 'retrieved', delivery_kind: 'published_cell', display_primary_eligible: true,
  },
}

const gfsCloud = {
  field: 'total_cloud', value: 88, key: 'total_cloud_geometric', family: 'cloud_cover', phase: null, storage: 'stored',
  provenance: {
    source_id: 'noaa-gfs', product: 'GFS', provider: 'NOAA', normalized_units: 'percent', data_mode: 'live',
    evidence_class: 'retrieved', delivery_kind: 'published_cell', display_primary_eligible: true,
  },
}

const cloudPair = {
  family: 'cloud_cover', a: 'total_cloud_opacity', b: 'total_cloud_geometric', comparable: false,
  reason: 'definition',
  detail: 'Opacity-weighted cover weights each layer by how much light it stops; geometric cover counts thin cirrus in full.',
}

describe('a family is what the response says it is, never what a key looks like', () => {
  it('groups a value under the family the response declared', () => {
    expect(resolveFamily('cloud_cover')).toBe('cloud_cover')
    const snapshot = normalizePoint(point([hrdpsCloud]))
    expect(snapshot.servedFields[0].attribution.family).toBe('cloud_cover')
    expect(snapshot.servedFields[0].attribution.fieldKey).toBe('total_cloud_opacity')
  })

  it('groups a value that declared no family under ungrouped, never by spelling', () => {
    // The field is named `total_cloud` and the catalogue copy knows three cloud
    // keys. It still must not be filed under cloud cover: the response declared
    // no family, and a family read off a name is exactly the collision the
    // catalogue exists to remove.
    const snapshot = normalizePoint(point([{ ...hrdpsCloud, family: undefined, key: undefined }]))
    expect(snapshot.servedFields[0].attribution.family).toBe(UNGROUPED_FAMILY)
    expect(snapshot.servedFields[0].attribution.fieldKey).toBeNull()
    expect(resolveFamily(undefined)).toBe(UNGROUPED_FAMILY)
    expect(resolveFamily('   ')).toBe(UNGROUPED_FAMILY)
  })

  it('orders families by the catalogue and puts ungrouped last', () => {
    const grouped = groupByFamily(
      [{ f: UNGROUPED_FAMILY }, { f: 'humidity' }, { f: 'cloud_cover' }],
      (item) => item.f,
    )
    expect(grouped.map((group) => group.family)).toEqual(['cloud_cover', 'humidity', UNGROUPED_FAMILY])
    expect(grouped[0].title).toBe('Cloud cover')
    expect(grouped[2].title).toBe('Ungrouped')
    expect(familyNote(UNGROUPED_FAMILY)).toContain('declared no field family')
  })

  it('names a family the copy has never heard of rather than folding it in', () => {
    expect(familyTitle('a_family_added_after_this_build')).toBe('a_family_added_after_this_build')
    expect(familyNote('a_family_added_after_this_build')).toBeNull()
  })

  it('shows each member’s key and definition, in the catalogue’s words', () => {
    expect(fieldDefinition('total_cloud_opacity')).toContain('weighted by how much light each layer stops')
    expect(fieldDefinition('total_cloud_geometric')).toContain('maximum-random overlap')
    // The unit and level travel with the definition: a cover in percent at the
    // whole column is not the same reading as one in eighths at a station.
    expect(fieldDefinition('total_cloud_geometric')).toContain('percent')
    expect(fieldDefinition(null)).toContain('no catalogue key')
    expect(fieldDefinition('a_key_the_copy_does_not_know')).toContain('no entry')
  })

  it('renders the served values grouped by family, key and definition beside each', async () => {
    vi.stubGlobal('fetch', routedFetch(point([hrdpsCloud, gfsCloud], { comparability: [cloudPair] })))
    render(<App />)
    const cloud = await screen.findByLabelText('Cloud cover family')
    expect(within(cloud).getByText('total_cloud_opacity')).toBeInTheDocument()
    expect(within(cloud).getByText('total_cloud_geometric')).toBeInTheDocument()
    // The family's own comparability note, verbatim from the catalogue.
    expect(within(cloud).getByText(/Opacity-weighted cover \(ECCC GEM/)).toBeInTheDocument()
    // And each member's definition.
    expect(within(cloud).getAllByText(/weighted by how much light each layer stops/).length).toBeGreaterThan(0)
    expect(within(cloud).getAllByText(/maximum-random overlap/).length).toBeGreaterThan(0)
  })
})

describe('two non-comparable members are never drawn as one thing', () => {
  it('reads the comparability list only as the response served it', () => {
    expect(parseComparability([cloudPair])).toHaveLength(1)
    // An entry missing `comparable` states nothing: reading it as `true` is the
    // one failure the list exists to prevent.
    expect(parseComparability([{ family: 'cloud_cover', a: 'x', b: 'y' }])).toHaveLength(0)
    expect(parseComparability(undefined)).toHaveLength(0)
  })

  it('answers a pair the response never mentioned as unstated, not comparable', () => {
    const index = buildComparabilityIndex([cloudPair])
    expect(comparabilityVerdict(index, 'total_cloud_opacity', 'total_cloud_geometric')).toBe('not-comparable')
    // Order does not matter: the pair is unordered.
    expect(comparabilityVerdict(index, 'total_cloud_geometric', 'total_cloud_opacity')).toBe('not-comparable')
    expect(comparabilityVerdict(index, 'total_cloud_opacity', 'total_cloud_mean_6h')).toBe('unstated')
  })

  it('states beside each member which siblings it may not be drawn with', async () => {
    vi.stubGlobal('fetch', routedFetch(point([hrdpsCloud, gfsCloud], { comparability: [cloudPair] })))
    render(<App />)
    const cloud = await screen.findByLabelText('Cloud cover family')
    const statements = within(cloud).getAllByText(/are never drawn on one/)
    expect(statements).toHaveLength(2)
    expect(statements[0]).toHaveTextContent('definition')
    expect(statements[0]).toHaveTextContent('weights each layer by how much light it stops')
  })
})

describe('a difference between non-comparable members is refused with the reason', () => {
  const index = buildComparabilityIndex([cloudPair])

  it('refuses with the response’s reason rather than a number', () => {
    const refusal = differenceRefusal(index, 'total_cloud_opacity', 'total_cloud_geometric')
    expect(refusal).toContain('are not comparable')
    expect(refusal).toContain('definition')
    expect(refusal).toContain('counts thin cirrus in full')
  })

  it('refuses an unstated pair too: silence is not permission', () => {
    expect(differenceRefusal(index, 'total_cloud_opacity', 'total_cloud_mean_6h')).toContain('No comparability statement was served')
  })

  it('permits a difference only where the response states the pair comparable', () => {
    const comparable = buildComparabilityIndex([{ family: 'wind', a: 'wind_speed_10m', b: 'wind_speed_10m_derived', comparable: true, reason: null, detail: null }])
    expect(differenceRefusal(comparable, 'wind_speed_10m', 'wind_speed_10m_derived')).toBeNull()
  })

  it('refuses HRDPS minus GFS cloud in the interface, showing the reason', async () => {
    vi.stubGlobal('fetch', routedFetch(point([hrdpsCloud, gfsCloud], { comparability: [cloudPair] })))
    render(<App />)
    const panel = await screen.findByLabelText('Difference between two family members')
    const user = userEvent.setup()
    await user.selectOptions(within(panel).getByLabelText('Difference member A'), 'total_cloud_opacity · eccc-hrdps')
    await user.selectOptions(within(panel).getByLabelText('Difference member B'), 'total_cloud_geometric · noaa-gfs')
    await user.click(within(panel).getByRole('button', { name: 'Show difference' }))
    const refusal = within(panel).getByText(/Difference refused/)
    expect(refusal).toHaveAttribute('data-difference', 'refused')
    expect(refusal).toHaveTextContent('are not comparable')
    // The arithmetic is 41 - 88 = -47. It must not appear anywhere.
    expect(within(panel).queryByText(/-47/)).not.toBeInTheDocument()
    expect(within(panel).queryByTestId('difference-shown')).not.toBeInTheDocument()
  })
})

describe('the legend changes when the map switches between non-comparable members', () => {
  const layer = (id: string, title: string, family: string | undefined, fieldKey: string): LayerItem => ({
    id, title, kind: 'raster', field: fieldKey, product: title, units: 'percent', semantics: 'cover',
    raster_available: true, legend_available: true, evidence_basis: 'published_artifact',
    ...(family === undefined ? {} : { family }),
  })
  const hrdps = layer('hrdps-cloud', 'HRDPS cloud', 'cloud_cover', 'total_cloud_opacity')
  const gfs = layer('gfs-cloud', 'GFS cloud', 'cloud_cover', 'total_cloud_geometric')

  it('draws a different definition for each member', () => {
    const { container, rerender } = render(<ActiveFamilyLegends layers={[hrdps]} />)
    const first = container.querySelector('[data-testid="legend-definition"]')!.textContent!
    expect(first).toContain('total_cloud_opacity')
    expect(first).toContain('Opacity-weighted')
    rerender(<ActiveFamilyLegends layers={[gfs]} />)
    const second = container.querySelector('[data-testid="legend-definition"]')!.textContent!
    expect(second).toContain('total_cloud_geometric')
    expect(second).toContain('Geometric maximum-random overlap')
    // The requirement in one line: switching members changed the legend.
    expect(second).not.toBe(first)
  })

  it('says the two ramps are separate when both members are on at once', () => {
    render(<ActiveFamilyLegends layers={[hrdps, gfs]} />)
    const statement = screen.getByText(/measured by different definitions/)
    expect(statement).toHaveAttribute('data-not-comparable', 'true')
    expect(statement).toHaveTextContent('are not one ramp')
  })

  it('judges layer pairs by the catalogue’s comparability group, and treats unknown as not the same', () => {
    expect(layerComparability('total_cloud_opacity', 'total_cloud_geometric')).toBe('different')
    expect(layerComparability('total_cloud_opacity', 'total_cloud_opacity')).toBe('same')
    expect(layerComparability('total_cloud_opacity', 'a_key_the_copy_does_not_know')).toBe('unstated')
  })

  it('groups layers by the declared family and leaves an undeclared one ungrouped', () => {
    const undeclared = layer('x', 'Something', undefined, 'total_cloud_opacity')
    expect(layerFamily(undeclared)).toBe(UNGROUPED_FAMILY)
    expect(layerFieldKey(undeclared)).toBe('total_cloud_opacity')
    const grouped = groupLayersByFamily([undeclared, hrdps, gfs])
    expect(grouped.map((group) => group.family)).toEqual(['cloud_cover', UNGROUPED_FAMILY])
    expect(grouped[0].members).toHaveLength(2)
    // An ungrouped layer is never told it conflicts with anything: no family
    // was declared, so no family statement can be made about it.
    render(<ActiveFamilyLegends layers={[undeclared]} />)
    expect(screen.queryByText(/measured by different definitions/)).not.toBeInTheDocument()
  })

  it('carries the same statement into the map’s text alternative', () => {
    expect(describeLayerFamilySentence(hrdps)).toContain('Field family Cloud cover')
    expect(describeLayerFamilySentence(hrdps)).toContain('total_cloud_opacity')
    expect(describeLayerFamilySentence(layer('x', 'Something', undefined, 'k'))).toContain('none declared')
  })
})

describe('available-not-stored and not-published are shown as themselves', () => {
  it('keeps the three storage answers apart, and refuses a fourth', () => {
    expect(resolveStorage('stored')).toBe('stored')
    expect(resolveStorage('available-not-stored')).toBe('available-not-stored')
    expect(resolveStorage('not-published')).toBe('not-published')
    for (const value of ['available_not_stored', 'blocked', 'aged_out', null, undefined, 7]) {
      expect(resolveStorage(value)).toBeNull()
    }
  })

  it('says something different for each of the five ways a value can be missing', () => {
    const sentences = new Set([
      unavailableSentence('available-not-stored', null),
      unavailableSentence('not-published', null),
      unavailableSentence('stored', 'null'),
      unavailableSentence('stored', 'blocked'),
      unavailableSentence('stored', 'aged_out'),
    ])
    expect(sentences.size).toBe(5)
    expect(unavailableSentence('available-not-stored', null)).toContain('does not store')
    expect(unavailableSentence('not-published', null)).toContain('does not publish this field at all')
    expect(unavailableSentence('stored', 'blocked')).toContain('credential')
    expect(unavailableSentence('stored', 'aged_out')).toContain('retention window')
    // A stored field with a value has nothing to explain.
    expect(unavailableSentence('stored', null)).toBeNull()
  })

  it('renders a GFS field the producer publishes and this deployment does not store', async () => {
    const notStored = {
      field: 'aerosol_optical_thickness', value: null, key: 'aerosol_optical_thickness', family: 'radiation',
      storage: 'available-not-stored', phase: null,
      provenance: {
        source_id: 'noaa-gfs', product: 'GFS', provider: 'NOAA', data_mode: 'unavailable',
        evidence_class: 'retrieved', display_primary_eligible: true,
      },
    }
    vi.stubGlobal('fetch', routedFetch(point([hrdpsCloud, notStored])))
    render(<App />)
    const families = await screen.findByLabelText('Readings by field family')
    const row = within(families).getByText('aerosol_optical_thickness').closest('li') as HTMLElement
    expect(within(row).getByText('Not stored here')).toBeInTheDocument()
    const line = row.querySelector('[data-storage="available-not-stored"]')!
    expect(line.textContent).toContain('The producer publishes this field')
    expect(line.textContent).toContain('this deployment does not store it')
    // And no number is invented for it.
    expect(within(row).queryByText(/^\d/)).not.toBeInTheDocument()
  })

  it('shows the source catalogue’s own field list with its storage answers', async () => {
    const sources: CatalogSource[] = [{
      id: 'noaa-gfs', producer: 'NOAA', product: 'GFS', state: 'implementing', status_reason: '',
      role: 'Global guidance', may_enter_consensus: false, cadence: '6 h', forecast_horizon: '384 h',
      geographic_coverage: 'Global', licence: 'Public domain', attribution: 'NOAA',
      fields: [
        { key: 'total_cloud_geometric', family: 'cloud_cover', storage: 'stored', upstream: 'TCDC', note: null },
        { key: 'aerosol_optical_thickness', family: 'radiation', storage: 'available-not-stored', upstream: 'AOTK', note: null },
        { key: 'wind_direction_10m', family: 'wind', storage: 'not-published', upstream: null, note: 'u and v only' },
      ],
    }]
    vi.stubGlobal('fetch', routedFetch(point([hrdpsCloud]), sources))
    render(<App />)
    const catalogue = await screen.findByLabelText('Fields by source and family')
    expect(catalogue.querySelector('[data-field-key="aerosol_optical_thickness"]')).toHaveAttribute('data-storage', 'available-not-stored')
    expect(catalogue.querySelector('[data-field-key="wind_direction_10m"]')).toHaveAttribute('data-storage', 'not-published')
    expect(within(catalogue).getByText(/does not publish this field at all/)).toBeInTheDocument()
  })
})

describe('an uncatalogued variable is refused, not rendered as a reading', () => {
  it('carries the flag through to the attribution', () => {
    const snapshot = normalizePoint(point([{
      field: 'temperature', value: null,
      provenance: {
        source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', data_mode: 'unavailable',
        evidence_class: 'retrieved', quality: { status: 'unknown', flags: ['uncatalogued_field'] },
      },
    }], { notices: ['temperature has no catalogue key; no value is served for it'] }))
    const attribution = snapshot.fieldSources.temperature
    expect(attribution.uncatalogued).toBe(true)
    expect(attribution.family).toBe(UNGROUPED_FAMILY)
    expect(attribution.notice).toContain('no catalogue key')
    expect(snapshot.temperatureC).toBeNull()
  })

  it('shows the notice in place of a value', async () => {
    vi.stubGlobal('fetch', routedFetch(point([
      hrdpsCloud,
      {
        field: 'visibility', value: null,
        provenance: {
          source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', data_mode: 'unavailable',
          evidence_class: 'retrieved', quality: { status: 'unknown', flags: ['uncatalogued_field'] },
        },
      },
    ], { notices: ['visibility has no catalogue key; no value is served for it'] })))
    render(<App />)
    const metric = (await screen.findByText('Visibility')).closest('.metric') as HTMLElement
    expect(within(metric).getByText('Unavailable')).toBeInTheDocument()
    expect(within(metric).getByText(/has no catalogue key/)).toBeInTheDocument()
  })
})

describe('the page renders against an API that serves none of this yet', () => {
  it('groups everything under ungrouped and states no comparability at all', async () => {
    const bare = {
      field: 'temperature', value: 12.4,
      provenance: {
        source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'degC', data_mode: 'live',
        evidence_class: 'retrieved', display_primary_eligible: true,
      },
    }
    const snapshot = normalizePoint(point([bare]))
    expect(snapshot.comparability).toEqual([])
    expect(snapshot.servedFields[0].attribution.storage).toBeNull()
    vi.stubGlobal('fetch', routedFetch(point([bare])))
    render(<App />)
    // The temperature still reads: an absent family is a gap in the response,
    // never a reason to blank a value the producer did publish.
    await screen.findByText(/12\.4/)
    // And no family panel is drawn, because nothing declared a family or a
    // key: an "Ungrouped" list repeating every metric would assert a grouping
    // the response never made.
    expect(screen.queryByLabelText('Readings by field family')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Difference between two family members')).not.toBeInTheDocument()
  })
})
