import { render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { normalizePoint, type ApiPointResponse } from './api'
import { ensembleMemberOptions, ensembleRowsOf, ensembleTextRows, groupEnsembleRows, isAveragedField } from './Ensemble'

vi.mock('./MapPanel', () => ({
  MapPanel: ({ label, evidence }: { label: string; evidence: Array<{ label: string; value: string }> }) => (
    <section aria-label={`${label} map pane`}>
      <dl aria-label="text alternative">
        {evidence.map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}
      </dl>
    </section>
  ),
}))

const response = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })

const point = (fields: unknown[], notices: string[] = []): ApiPointResponse => ({
  data_mode: 'live',
  valid_time: '2026-09-02T15:00:00Z',
  selection: { mode: 'evidence_only', badge: 'Evidence only', selected_source_id: 'eccc-reps', selected_product_id: 'reps' },
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

const runTime = '2026-09-02T00:00:00Z'

const memberSet = (overrides: Partial<Record<string, unknown>> = {}) => ({
  family: 'eccc-reps', source_id: 'eccc-reps', run_time: runTime,
  members_declared: 21, members_used: 21, members_missing: [], control_included: true, partial: false,
  ...overrides,
})

const memberField07 = {
  field: 'wind_speed', value: 12.3,
  provenance: {
    source_id: 'eccc-reps', product: 'REPS', provider: 'ECCC', normalized_units: 'm/s', data_mode: 'live',
    evidence_class: 'retrieved', display_primary_eligible: true,
    member: '07', member_control: false,
    ensemble: { family: 'eccc-reps', statistic: null, computed_here: false, member_set: memberSet(), refusal: null, quantile: null, threshold: null, threshold_units: null, comparison: null, averaging_window_hours: null },
  },
}

const controlField = {
  field: 'wind_speed', value: 11.0,
  provenance: {
    source_id: 'eccc-reps', product: 'REPS', provider: 'ECCC', normalized_units: 'm/s', data_mode: 'live',
    evidence_class: 'retrieved', display_primary_eligible: true,
    member: '00', member_control: true,
    ensemble: { family: 'eccc-reps', statistic: null, computed_here: false, member_set: memberSet(), refusal: null, quantile: null, threshold: null, threshold_units: null, comparison: null, averaging_window_hours: null },
  },
}

const statisticField = {
  field: 'wind_speed_ensemble_mean', value: 11.8,
  provenance: {
    source_id: 'eccc-reps', product: 'REPS', provider: 'ECCC', normalized_units: 'm/s', data_mode: 'live',
    evidence_class: 'derived_here', derivation: 'ensemble_mean', display_primary_eligible: true,
    member: null, member_control: null,
    ensemble: {
      family: 'eccc-reps', statistic: 'ensemble_mean', computed_here: true,
      member_set: memberSet({ members_used: 18, members_missing: ['03', '09', '15'], partial: true }),
      refusal: null, quantile: null, threshold: null, threshold_units: null, comparison: null, averaging_window_hours: null,
    },
  },
}

const refusedField = {
  field: 'wind_speed_ensemble_spread', value: null,
  provenance: {
    source_id: 'eccc-reps', product: 'REPS', provider: 'ECCC', normalized_units: 'm/s', data_mode: 'live',
    evidence_class: 'derived_here', display_primary_eligible: true,
    quality: { status: 'unavailable', flags: ['statistic_refused'] },
    member: null, member_control: null,
    ensemble: {
      family: 'eccc-reps', statistic: 'ensemble_spread', computed_here: true, member_set: null,
      refusal: 'fewer than the minimum member count', quantile: null, threshold: null, threshold_units: null, comparison: null, averaging_window_hours: null,
    },
  },
}

const providerReductionField = {
  field: 'wind_speed_ensemble_mean', value: 13.1,
  provenance: {
    source_id: 'eccc-geps', product: 'GEPS', provider: 'ECCC', normalized_units: 'm/s', data_mode: 'live',
    evidence_class: 'retrieved', display_primary_eligible: true,
    member: null, member_control: null,
    ensemble: {
      family: 'eccc-geps', statistic: 'ensemble_mean', computed_here: false,
      member_set: { family: 'eccc-geps', source_id: 'eccc-geps', run_time: runTime, members_declared: 20, members_used: 20, members_missing: [], control_included: null, partial: false },
      refusal: null, quantile: null, threshold: null, threshold_units: null, comparison: null, averaging_window_hours: null,
    },
  },
}

const averagedCloudField = {
  field: 'total_cloud_mean_6h', value: 55,
  provenance: {
    source_id: 'noaa-gefs', product: 'GEFS', provider: 'NOAA', normalized_units: 'percent', data_mode: 'live',
    evidence_class: 'retrieved', display_primary_eligible: true,
    member: '05', member_control: false,
    ensemble: {
      family: 'noaa-gefs', statistic: null, computed_here: false,
      member_set: { family: 'noaa-gefs', source_id: 'noaa-gefs', run_time: runTime, members_declared: 31, members_used: 31, members_missing: [], control_included: false, partial: false },
      refusal: null, quantile: null, threshold: null, threshold_units: null, comparison: null, averaging_window_hours: 6,
    },
  },
}

const instantaneousCloudMember = {
  field: 'total_cloud', value: 40,
  provenance: {
    source_id: 'noaa-gefs', product: 'GEFS', provider: 'NOAA', normalized_units: 'percent', data_mode: 'live',
    evidence_class: 'retrieved', display_primary_eligible: true,
    member: '05', member_control: false,
    ensemble: {
      family: 'noaa-gefs', statistic: null, computed_here: false,
      member_set: { family: 'noaa-gefs', source_id: 'noaa-gefs', run_time: runTime, members_declared: 31, members_used: 31, members_missing: [], control_included: false, partial: false },
      refusal: null, quantile: null, threshold: null, threshold_units: null, comparison: null, averaging_window_hours: null,
    },
  },
}

describe('ensemble rows: unit-level labelling', () => {
  it('labels a member row with family, run, member (naming the control), and member set', () => {
    const snapshot = normalizePoint(point([memberField07]))
    const rows = ensembleRowsOf(snapshot.servedFields)
    expect(rows).toHaveLength(1)
    expect(rows[0].kind).toBe('member')
    expect(rows[0].text).toContain('eccc-reps')
    expect(rows[0].text).toContain(runTime)
    expect(rows[0].text).toContain('member 07')
    expect(rows[0].text).toContain('21 of 21 members')
  })

  it('names the control member', () => {
    const snapshot = normalizePoint(point([controlField]))
    const rows = ensembleRowsOf(snapshot.servedFields)
    expect(rows[0].text).toContain('member 00 (control)')
  })

  it('labels a computed statistic with all four names, and names the missing members of a partial set', () => {
    const snapshot = normalizePoint(point([statisticField]))
    const rows = ensembleRowsOf(snapshot.servedFields)
    expect(rows[0].kind).toBe('statistic')
    expect(rows[0].text).toContain('eccc-reps')
    expect(rows[0].text).toContain(runTime)
    expect(rows[0].text).toContain('ensemble_mean')
    expect(rows[0].text).toContain('18 of 21 members')
    expect(rows[0].text).toContain('missing 03, 09, 15')
    expect(rows[0].text).toContain('computed here')
  })

  it('labels a refused statistic with the refusal reason and no provider/computed-here claim it cannot make', () => {
    const snapshot = normalizePoint(point([refusedField]))
    const rows = ensembleRowsOf(snapshot.servedFields)
    expect(rows[0].kind).toBe('refused')
    expect(rows[0].text).toContain('ensemble_spread')
    expect(rows[0].text).toContain('refused: fewer than the minimum member count')
  })

  it('labels a provider reduction as the provider’s own, not computed here', () => {
    const snapshot = normalizePoint(point([providerReductionField]))
    const rows = ensembleRowsOf(snapshot.servedFields)
    expect(rows[0].kind).toBe('provider_reduction')
    expect(rows[0].text).toContain('eccc-geps')
    expect(rows[0].text).toContain("provider's own")
    expect(rows[0].text).not.toContain('computed here')
  })

  it('fences an averaged field into its own group, apart from an instantaneous cloud row', () => {
    const snapshot = normalizePoint(point([averagedCloudField, instantaneousCloudMember]))
    expect(isAveragedField(snapshot.servedFields[0])).toBe(true)
    expect(isAveragedField(snapshot.servedFields[1])).toBe(false)
    const rows = ensembleRowsOf(snapshot.servedFields)
    const { standard, averaged } = groupEnsembleRows(rows)
    expect(averaged).toHaveLength(1)
    expect(averaged[0].field).toBe('total_cloud_mean_6h')
    expect(averaged[0].text).toContain('6 h mean, not comparable with instantaneous cloud')
    expect(standard).toHaveLength(1)
    expect(standard[0].field).toBe('total_cloud')
    expect(standard[0].text).not.toContain('6 h mean')
  })

  it('carries the same labels into the text alternative', () => {
    const snapshot = normalizePoint(point([statisticField]))
    const textRows = ensembleTextRows(snapshot)
    expect(textRows).toHaveLength(1)
    expect(textRows[0].value).toContain('ensemble_mean')
    expect(textRows[0].value).toContain('18 of 21 members')
    expect(textRows[0].value).toContain('computed here')
  })

  it('collects the distinct members the response served, control named, for the selector', () => {
    const snapshot = normalizePoint(point([memberField07, controlField]))
    const options = ensembleMemberOptions(snapshot)
    expect(options).toHaveLength(2)
    expect(options.find((o) => o.value === '00')).toEqual({ value: '00', label: '00 (control)', control: true })
    expect(options.find((o) => o.value === '07')).toEqual({ value: '07', label: '07', control: false })
  })
})

describe('the panel and the text alternative, rendered', () => {
  it('renders a member row, a statistic row, a refused row and a provider-reduction row, each with all four names', async () => {
    vi.stubGlobal('fetch', routedFetch(point([memberField07, statisticField, refusedField, providerReductionField])))
    render(<App />)
    const panel = await screen.findByLabelText('Ensemble members and statistics')
    const memberRow = within(panel).getByText(/member 07/).closest('li') as HTMLElement
    expect(memberRow).toHaveTextContent('eccc-reps')
    expect(memberRow).toHaveTextContent(runTime)
    expect(memberRow).toHaveTextContent('21 of 21 members')

    const statisticRow = panel.querySelector('[data-ensemble-kind="statistic"]') as HTMLElement
    expect(statisticRow).toHaveTextContent('ensemble_mean')
    expect(statisticRow).toHaveTextContent('computed here')
    expect(statisticRow).toHaveTextContent('18 of 21 members')
    expect(statisticRow).toHaveTextContent('missing 03, 09, 15')

    const refusedRow = within(panel).getByText(/ensemble_spread/).closest('li') as HTMLElement
    expect(refusedRow).toHaveTextContent('refused: fewer than the minimum member count')

    const reductionRow = within(panel).getByText(/eccc-geps/).closest('li') as HTMLElement
    expect(reductionRow).toHaveTextContent("provider's own")
    expect(reductionRow).not.toHaveTextContent('computed here')

    // The same four names appear in the text alternative, not only visually.
    const textAlternative = screen.getByLabelText('text alternative')
    expect(within(textAlternative).getByText(/missing 03, 09, 15/)).toBeInTheDocument()
    expect(within(textAlternative).getByText(/refused: fewer than the minimum member count/)).toBeInTheDocument()
  })

  it('groups the averaged-cloud row apart from an instantaneous cloud row', async () => {
    vi.stubGlobal('fetch', routedFetch(point([averagedCloudField, instantaneousCloudMember])))
    render(<App />)
    const panel = await screen.findByLabelText('Ensemble members and statistics')
    const averagedGroup = panel.querySelector('[data-ensemble-group="averaged"].ensemble-averaged-group') as HTMLElement
    expect(averagedGroup).toBeTruthy()
    expect(within(averagedGroup).getAllByText(/6 h mean, not comparable with instantaneous cloud/).length).toBeGreaterThan(0)
    expect(averagedGroup.querySelector('[data-field="total_cloud_mean_6h"]')).toBeTruthy()
    const standardGroup = panel.querySelector('ul.ensemble-rows[data-ensemble-group="standard"]') as HTMLElement
    expect(standardGroup).toBeTruthy()
    expect(standardGroup.querySelector('[data-field="total_cloud"]')).toBeTruthy()
    expect(within(standardGroup).queryByText(/6 h mean/)).not.toBeInTheDocument()
  })

  it('sends the selected member as a request parameter', async () => {
    const fetchMock = routedFetch(point([memberField07, controlField]))
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    const { fireEvent } = await import('@testing-library/react')
    // The member selector lives in the expert (Workbench) layout.
    fireEvent.click(screen.getByRole('button', { name: 'Workbench' }))
    await waitFor(() => expect(screen.getAllByLabelText('Member').length).toBeGreaterThan(0))
    const [select] = screen.getAllByLabelText('Member') as HTMLSelectElement[]
    expect(select.tagName).toBe('SELECT')
    expect(select).not.toBeDisabled()
    fireEvent.change(select, { target: { value: '07' } })
    await waitFor(() => {
      const calls = fetchMock.mock.calls.map((call) => String(call[0]))
      expect(calls.some((url) => url.includes('/point') && url.includes('member=07'))).toBe(true)
    })
  })

  it('disables the member control with a reason when the response carries no member row', async () => {
    vi.stubGlobal('fetch', routedFetch(point([{
      field: 'temperature', value: 4,
      provenance: { source_id: 'eccc-hrdps', product: 'HRDPS', provider: 'ECCC', normalized_units: 'degC', data_mode: 'live', evidence_class: 'retrieved', display_primary_eligible: true },
    }])))
    render(<App />)
    const { fireEvent } = await import('@testing-library/react')
    fireEvent.click(screen.getByRole('button', { name: 'Workbench' }))
    await waitFor(() => expect(screen.getAllByLabelText('Member').length).toBeGreaterThan(0))
    const [select] = screen.getAllByLabelText('Member') as HTMLSelectElement[]
    expect(select).toBeDisabled()
    expect(screen.getAllByText('No ensemble member in returned provenance').length).toBeGreaterThan(0)
  })
})
