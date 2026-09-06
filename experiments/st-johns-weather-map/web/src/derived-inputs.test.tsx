import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { normalizePoint, type ApiPointResponse } from './api'

vi.mock('./MapPanel', () => ({
  MapPanel: ({ label }: { label: string }) => <section aria-label={`${label} map pane`} />,
}))

const response = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })

const point = (fields: unknown[]): ApiPointResponse => ({
  data_mode: 'live',
  valid_time: '2026-09-02T15:00:00Z',
  selection: { mode: 'fallback', badge: 'HRDPS primary', selected_source_id: 'eccc-hrdps', selected_product_id: 'hrdps' },
  fields,
} as unknown as ApiPointResponse)

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

const temperature = {
  field: 'temperature', value: 12.4,
  provenance: { source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'degC', data_mode: 'live', evidence_class: 'retrieved' },
}

/** Relative humidity as `point-evidence-sampling` says a derived value must
 *  arrive: the class, the registry entry with version and citation, both
 *  inputs with their own provenance, and the worse input's quality carrying
 *  the `derived` flag. */
const derivedHumidity = {
  field: 'relative_humidity', value: 79.5,
  provenance: {
    source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'percent', data_mode: 'live',
    evidence_class: 'derived_here',
    derivation: 'relative_humidity_from_dewpoint',
    derivation_version: 'metpy-1.7.1-liquid-v1',
    derivation_citation: 'Bolton (1980), Mon. Wea. Rev. 108, 1046-1053',
    quality: { status: 'suspect', flags: ['derived'] },
    derivation_inputs: [
      { field: 'temperature', source_id: 'eccc-hrdps', product: 'HRDPS', valid_time: '2026-09-02T15:00:00Z', quality: { status: 'passed', flags: [] }, evidence_class: 'retrieved' },
      { field: 'dew_point', source_id: 'eccc-hrdps', product: 'HRDPS', valid_time: '2026-09-02T15:00:00Z', quality: 'suspect', evidence_class: 'retrieved' },
    ],
  },
}

describe('a derived value carries its inputs and method', () => {
  it('reads the method, quality and every input off provenance', () => {
    const snapshot = normalizePoint(point([temperature, derivedHumidity]))
    const humidity = snapshot.fieldSources.relative_humidity
    expect(humidity.evidenceClass).toBe('derived_here')
    expect(humidity.derivationMethod).toEqual({
      name: 'relative_humidity_from_dewpoint',
      version: 'metpy-1.7.1-liquid-v1',
      citation: 'Bolton (1980), Mon. Wea. Rev. 108, 1046-1053',
    })
    expect(humidity.qualityStatus).toBe('suspect')
    expect(humidity.qualityFlags).toContain('derived')
    expect(humidity.derivationInputs.map((input) => input.field)).toEqual(['temperature', 'dew_point'])
    // Quality arrives either as the object form or a bare status string; both
    // reach the reader as the status, never as "[object Object]".
    expect(humidity.derivationInputs.map((input) => input.quality)).toEqual(['passed', 'suspect'])
    expect(humidity.derivationInputs.every((input) => input.evidenceClass === 'retrieved')).toBe(true)
  })

  it('prefers the object form of the method when the response carries one', () => {
    const snapshot = normalizePoint(point([{
      field: 'relative_humidity', value: 80,
      provenance: {
        source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'percent', data_mode: 'live',
        evidence_class: 'derived_here',
        derivation: 'a sentence, not a registry entry',
        derivation_method: { name: 'relative_humidity_from_dewpoint', version: '2.0.0', citation: 'Bolton (1980)' },
      },
    }]))
    expect(snapshot.fieldSources.relative_humidity.derivationMethod?.name).toBe('relative_humidity_from_dewpoint')
    expect(snapshot.fieldSources.relative_humidity.derivationMethod?.version).toBe('2.0.0')
  })

  it('reads no inputs or method for a value that is not derived here', () => {
    // A reprocessed value may name a `derivation`, but it is the
    // intermediary's sentence, not a registered method this deployment cites.
    const snapshot = normalizePoint(point([{
      field: 'total_cloud', value: 44,
      provenance: {
        source_id: 'open-meteo-weathernext2', product: 'WeatherNext 2 via Open-Meteo', provider: 'Google',
        normalized_units: 'percent', data_mode: 'live', evidence_class: 'intermediary_derived',
        derivation: 'Open-Meteo cloud cover from the humidity profile',
        derivation_inputs: [{ field: 'relative_humidity', source_id: 'open-meteo-weathernext2' }],
      },
    }]))
    // Never the reading, so it reaches the reader as an alternative; its
    // attribution is what carries the class and the (absent) method.
    const cloud = snapshot.fieldAlternatives.total_cloud[0].attribution
    expect(cloud.evidenceClass).toBe('intermediary_derived')
    expect(cloud.derivationMethod).toBeNull()
    expect(cloud.derivationInputs).toEqual([])
    expect(snapshot.fieldSources.total_cloud).toBeUndefined()
  })

  it('shows the inputs and method on demand, and not before', async () => {
    vi.stubGlobal('fetch', routedFetch(point([temperature, derivedHumidity])))
    render(<App />)
    const humidity = await waitFor(() => screen.getByText('Humidity').closest('.metric') as HTMLElement)
    await waitFor(() => expect(within(humidity).getByText('80%')).toBeInTheDocument())

    // Disclosure, not the reading: the panel is closed until the reader asks.
    const disclosure = within(humidity).getByText('Humidity: inputs and method')
    expect(within(humidity).queryByText(/Bolton \(1980\)/)).not.toBeVisible()

    await userEvent.click(disclosure)
    expect(within(humidity).getByText(/relative_humidity_from_dewpoint/)).toBeVisible()
    expect(within(humidity).getByText(/metpy-1\.7\.1-liquid-v1/)).toBeVisible()
    expect(within(humidity).getByText(/Bolton \(1980\)/)).toBeVisible()
    // The quality is the worse input's, with the derived flag beside it.
    expect(within(humidity).getByText(/Quality: suspect · flags derived/)).toBeVisible()

    const inputs = within(humidity).getAllByRole('listitem')
    expect(inputs).toHaveLength(2)
    expect(inputs[0]).toHaveTextContent('temperature')
    expect(inputs[0]).toHaveTextContent('eccc-hrdps')
    expect(inputs[0]).toHaveTextContent('2026-09-02T15:00:00Z')
    expect(inputs[0]).toHaveTextContent('quality passed')
    expect(within(inputs[0]).getByText('retrieved')).toHaveAttribute('data-evidence-class', 'retrieved')
    expect(inputs[1]).toHaveTextContent('dew_point')
    expect(inputs[1]).toHaveTextContent('quality suspect')
  })

  it('says a derived value listed no inputs rather than showing an empty panel', async () => {
    vi.stubGlobal('fetch', routedFetch(point([temperature, {
      field: 'relative_humidity', value: 79.5,
      provenance: {
        source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'percent', data_mode: 'live',
        evidence_class: 'derived_here',
      },
    }])))
    render(<App />)
    const humidity = await waitFor(() => screen.getByText('Humidity').closest('.metric') as HTMLElement)
    await userEvent.click(within(humidity).getByText('Humidity: inputs and method'))
    expect(within(humidity).getByText('The response listed no inputs for this derived value.')).toBeVisible()
    expect(within(humidity).getByText(/named no derivation method/)).toBeVisible()
  })

  it('offers no such disclosure for a retrieved value', async () => {
    vi.stubGlobal('fetch', routedFetch(point([temperature, {
      field: 'relative_humidity', value: 79.5,
      provenance: { source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'percent', data_mode: 'live', evidence_class: 'retrieved' },
    }])))
    render(<App />)
    const humidity = await waitFor(() => screen.getByText('Humidity').closest('.metric') as HTMLElement)
    await waitFor(() => expect(within(humidity).getByText('80%')).toBeInTheDocument())
    expect(within(humidity).queryByText('Humidity: inputs and method')).not.toBeInTheDocument()
  })
})
