import { DiscoveryFilters } from './DiscoveryBrowser'
import { discoveryEntries, matchesDiscovery, type Filters } from './discovery'
import { SourceTag, sourceAttributes } from './SourceTag'
import { NativeTrack, selectedEvidence, type SharedSeriesSelection } from './NativeSeries'
import { layerMapping, layerImagery } from './layerIdentity'
import { useState } from 'react'
import type { CatalogSource, LayerItem, ServedFieldValue, SourceStatusItem, ObservationUnavailable } from '../types'
import { familyTitle, fieldDefinition, UNGROUPED_FAMILY } from '../fieldFamily'
import { EvidenceGlyph, EvidenceLedger, type InspectedEvidence } from './EvidenceInspector'
import type { DrawEvidence } from './MapStack'

interface Props {
  catalog: CatalogSource[]; statuses: SourceStatusItem[] | null; fields: ServedFieldValue[]; layers: LayerItem[]; drawn: DrawEvidence[]
  observationUnavailable?: ObservationUnavailable[]
  nativeSelection?: SharedSeriesSelection | null
  instant: number; catalogError: string | null; statusError: string | null
  onInspect: (evidence: InspectedEvidence, opener: HTMLButtonElement) => void
}
export function sourceEvidence(id: string, catalog: CatalogSource[], statuses: SourceStatusItem[] | null, fields: ServedFieldValue[], layers: LayerItem[] = [], nativeSelection: SharedSeriesSelection | null = null, observationUnavailable: ObservationUnavailable[] = []): InspectedEvidence {
  return { key: `source:${id}`, label: id, text: 'Registry declaration, acquisition status and returned point evidence have separate scopes.', details: {
    'Source identity': id,
    'Observation failure at Focus': observationUnavailable.filter((outcome) => outcome.source_id === id).map(({ source_id, reason, error_type, values_withheld }) => ({ source_id, reason, error_type, values_withheld })),
    'Registry declaration': catalog.find((source) => source.id === id) ?? 'Not present in the returned catalogue',
    'Delivery configuration': statuses?.find((status) => status.source_id === id)?.configuration ?? 'Configuration unknown; no successful access is inferred',
    'Delivery capabilities': catalog.find((source) => source.id === id)?.capabilities ?? 'No delivery descriptors supplied',
    'Acquisition status': statuses?.find((status) => status.source_id === id) ?? 'Not supplied; successful point retrieval is not inferred',
    'Returned evidence at Focus': fields.filter((field) => field.attribution.sourceId === id).map((field) => ({ field: field.field, text: field.text, has_value: field.hasValue, provenance: field.attribution.responseProvenance })),
    'Explicitly associated layers': layers.filter((layer) => layerMapping(layer).fields.some((row) => row.source_id === id)).map((layer) => ({ id: layer.id, mapping: layerMapping(layer), imagery: layerImagery(layer), listed_times: layer.times ?? [], freshness_assessed_at: layer.freshness_assessed_at ?? null })),
    'Finite native Series selection': nativeSelection ? { id: nativeSelection.snapshot.id, selected_at: nativeSelection.snapshot.selected_at, expires_at: nativeSelection.snapshot.expires_at, identities: nativeSelection.snapshot.identities.filter((identity) => identity.source_id === id), expired: nativeSelection.expired, complete: nativeSelection.complete, coordinates: { latitude: nativeSelection.selection.latitude, longitude: nativeSelection.selection.longitude }, window: { start: nativeSelection.selection.start, end: nativeSelection.selection.end }, rows: nativeSelection.series.filter((row) => row.source_id === id).map((row) => ({ ...row, samples: nativeSelection.expired ? [] : row.samples })) } : 'No native Series selection at this Focus',
    'Coverage limitation': 'Declared geography, a retrieval timestamp or a layer listing does not establish availability at this coordinate and time.',
  } }
}
/** State lives with App, preserving filters and selection across stage/dock changes. */
export function useSourcesView(props: Props) {
  const [perspective, setPerspective] = useState('Ledger')
  const [query, setQuery] = useState('')
  const [family, setFamily] = useState('')
  const [discoveryFilters, setDiscoveryFilters] = useState<Filters>({})
  const [selected, setSelected] = useState<string | null>(null)
  const { catalog, statuses, fields, layers, drawn, instant, onInspect, nativeSelection = null, observationUnavailable = [] } = props
  const nativeFamilies = (row: NonNullable<typeof nativeSelection>['series'][number]) => nativeSelection?.families?.[row.selector_id]?.length ? nativeSelection.families[row.selector_id] : [UNGROUPED_FAMILY]
  const allIds = [...new Set([...observationUnavailable.map((outcome) => outcome.source_id),...(nativeSelection?.series.map((row) => row.source_id) ?? []), ...catalog.map((source) => source.id), ...fields.flatMap((field) => field.attribution.sourceId ? [field.attribution.sourceId] : []), ...(statuses ?? []).map((status) => status.source_id), ...layers.flatMap((layer) => layerMapping(layer).fields.map((row) => row.source_id))])]
  const families = [...new Set([...(nativeSelection?.series.flatMap(nativeFamilies) ?? []), ...catalog.flatMap((source) => source.fields?.map((field) => field.family) ?? []), ...fields.map((field) => field.attribution.family)].filter((value): value is string => typeof value === 'string' && value.length > 0))].sort()
  const discovery = discoveryEntries(catalog, layers)
  const visible = allIds.filter((id) => {
    const entry = discovery.find(e => e.id === id)
    if (entry && !matchesDiscovery(entry, query, discoveryFilters)) return false
    const source = catalog.find((entry) => entry.id === id)
    const values = fields.filter((field) => field.attribution.sourceId === id)
    return (entry !== undefined || [id, source?.producer, source?.product, ...(nativeSelection?.series.filter((row) => row.source_id === id).map((row) => row.field) ?? []), ...source?.fields?.map((field) => field.key) ?? []].join(' ').toLowerCase().includes(query.trim().toLowerCase()))
      && (!family || source?.fields?.some((field) => field.family === family) || values.some((field) => field.attribution.family === family) || nativeSelection?.series.some((row) => row.source_id === id && nativeFamilies(row).includes(family)))
  })
  function inspect(id: string, opener: HTMLButtonElement) { setSelected(id); onInspect(sourceEvidence(id, catalog, statuses, fields, layers, nativeSelection, observationUnavailable), opener) }
  const inspectButton = (id: string) => <button aria-pressed={selected === id} onClick={(event) => inspect(id, event.currentTarget)}>Inspect source {id}</button>
  const readings = (id: string) => fields.filter((field) => field.attribution.sourceId === id && (!family || field.attribution.family === family))
  return <section className="sources-view" aria-label="Source evidence catalogue">
    <div className="sources-controls"><div role="group" aria-label="Sources perspective">{['Ledger', 'Family finder', 'Coverage lanes'].map((name) => <button key={name} aria-pressed={perspective === name} onClick={() => setPerspective(name)}>{name}</button>)}</div>
      <DiscoveryFilters label="Find source or field" onClear={() => setFamily('')} entries={discovery} query={query} setQuery={setQuery} filters={discoveryFilters} setFilters={setDiscoveryFilters} />
      <label>Field family<select value={family} onChange={(event) => setFamily(event.target.value)}><option value="">All families</option>{families.map((name) => <option key={name} value={name}>{familyTitle(name)}</option>)}</select></label>

    </div>
    <p>Declared capability, successful acquisition and evidence at Focus are separate facts. Native samples and listed frames do not imply continuous or geographic coverage.</p>
    {props.catalogError && <p>Catalogue unreadable: {props.catalogError}</p>}{props.statusError && <p>Acquisition status unreadable: {props.statusError}</p>}
    <p role="status" aria-atomic="true">{visible.length} sources match. {selected && <>Inspected source: {selected}{!visible.includes(selected) && ' (outside the current filters)'}</>}</p>
    {perspective === 'Ledger' && <div className="sources-table"><table><caption>Source Ledger at the shared Focus</caption><thead><tr><th scope="col">Source</th><th scope="col">Declared capability</th><th scope="col">Acquisition report</th><th scope="col">Returned point evidence</th><th scope="col">Provenance</th></tr></thead><tbody>
      {visible.map((id) => {
        const source = catalog.find((entry) => entry.id === id), status = statuses?.find((entry) => entry.source_id === id), values = readings(id)
        return <tr key={id} data-selected={selected === id}><th scope="row"><SourceTag id={id} /><small>{source?.producer ?? 'Producer not declared'} · {source?.product ?? 'Product not declared'}</small></th>
          <td>{source?.state ?? 'Registry state unknown'}<small>{source?.status_reason}</small><small>{source?.geographic_coverage ?? 'Geography not declared'}</small><small>{source?.fields ? `${source.fields.length} declared fields` : 'Fields not declared'}</small><small>{source?.capabilities ? `${source.capabilities.filter((capability) => capability.native_series).length} declared native Series paths` : 'Delivery paths not declared'}. This does not establish available samples.</small></td>
          <td>{status ? `${status.state} · ${status.data_mode}` : 'Acquisition status unknown'}<small>{status?.last_retrieval ? `Reported retrieval ${status.last_retrieval}` : 'No retrieval time supplied'}</small><small>{status?.detail}</small><small>Configuration: {status?.configuration?.state ?? 'unknown'}</small><small>{status?.configuration?.reason ?? 'Configuration not assessed; access is not inferred'}</small><small>Configuration checked: {status?.configuration?.checked_at ?? 'not supplied'}</small>{status?.configuration?.required_environment?.length ? <small>Required setting names: {status.configuration.required_environment.join(', ')}</small> : null}</td>
          <td>{observationUnavailable.filter((outcome) => outcome.source_id === id).map((outcome, index) => <small key={index}>Observation {outcome.reason} · {outcome.error_type}. Values withheld; selected model unchanged.</small>)}{values.length ? `${values.length} returned readings; inspect their individual availability` : 'No readings returned at Focus; coverage unestablished'}</td><td>{inspectButton(id)}</td></tr>
      })}
    </tbody></table></div>}
    {perspective === 'Family finder' && <div>{(family ? [family] : families).map((name) => {
      const declarations = visible.flatMap((id) => catalog.find((source) => source.id === id)?.fields?.filter((field) => field.family === name).map((field) => ({ id, field })) ?? [])
      return <section className="source-family-card" key={name}><h3>{familyTitle(name)}</h3>{declarations.length === 0 && <p>No matching field declaration was returned.</p>}
        <ul>{declarations.map(({ id, field }) => <li key={`${id}:${field.key}`}><strong>{field.key}</strong> · <SourceTag id={id} /><p>{fieldDefinition(field.key)}</p><p>Declared storage: {field.storage ?? 'unknown'} · Native field: {field.upstream ?? 'not supplied'}</p>{field.note && <p>{field.note}</p>}{inspectButton(id)}</li>)}</ul>
      </section>
    })}</div>}
    {perspective === 'Coverage lanes' && <div><p>Each marker is a returned native timestamp, within 24 hours either side of Focus. Unmarked spans are unqueried. × means a returned reading is absent or withheld, not an all-clear.</p>
      {visible.map((id) => <section className="source-coverage-lane" key={id}><h3><SourceTag id={id} /></h3><CoverageMarks values={readings(id)} instant={instant} />
        {readings(id).length === 0 && <p>No point samples were returned. Declared horizon and retrieval status do not fill this lane.</p>}
        {inspectButton(id)}<details><summary>Native values and absence states · {readings(id).length} readings</summary><EvidenceLedger rows={readings(id)} onInspect={onInspect} /></details>
      </section>)}
    </div>}
    {selected && perspective !== 'Coverage lanes' && <details className="source-selected-values"><summary>Returned values from {selected}</summary><EvidenceLedger rows={readings(selected)} onInspect={onInspect} /></details>}
    {nativeSelection && <section aria-label="Finite native Series evidence"><h3>Finite native Series selection</h3>
      <p>Selection {nativeSelection.snapshot.id} · Selected {nativeSelection.snapshot.selected_at} · Fixed expiry {nativeSelection.snapshot.expires_at}. {nativeSelection.complete ? 'All pages loaded.' : 'Partial selection: only loaded pages appear here. Continue in Series to read more.'}</p>
      <p>Point {nativeSelection.selection.latitude}, {nativeSelection.selection.longitude} · {nativeSelection.selection.start} to {nativeSelection.selection.end}. These are selected native readings, separate from point evidence at the exact Focus and from a source coverage declaration.</p>
      {nativeSelection.expired ? <p role="status">Native selection expired. Values are withheld; open Series and explicitly refresh to acquire another selection.</p> : nativeSelection.series.filter((row) => visible.includes(row.source_id) && (!family || nativeFamilies(row).includes(family))).map((row) => <NativeTrack key={row.selector_id} row={row} start={Date.parse(nativeSelection.selection.start)} end={Date.parse(nativeSelection.selection.end)} onInspect={(evidence, opener) => onInspect(selectedEvidence(evidence, nativeSelection.snapshot), opener)} />)}
      {nativeSelection.expired && <ul>{nativeSelection.series.filter((row) => visible.includes(row.source_id) && (!family || nativeFamilies(row).includes(family))).map((row) => <li key={row.selector_id}>{row.source_id} · {row.field} · Requested run {row.requested_run} · expired, no values shown</li>)}</ul>}
    </section>}
    <details className="sources-unmapped"><summary>Layer frame identities · {layers.length} layers</summary><p>Explicit source-to-field associations are declarations. Listed samples, advertised imagery and actual draw receipts stay separate; no join is inferred from a title or product.</p>
      {layers.filter((layer) => `${layer.id} ${layer.title}`.toLowerCase().includes(query.toLowerCase())).map((layer) => {
        const actual = drawn.find((entry) => entry.id === layer.id)
        const mapping = layerMapping(layer), availability = layerImagery(layer)
        return <section key={layer.id}><h3>{layer.title}</h3><p>Layer {layer.id} · Source mapping {mapping.status} · Field {layer.field_key ?? 'not supplied'}</p>
          <p>{mapping.reason}</p><ul>{mapping.fields.map((row, index) => <li key={index}>{row.source_id} · {row.field_key ?? `Unmapped declared field: ${row.declared_field ?? 'not supplied'}`}</li>)}</ul>
          <p>Imagery availability: {availability.status} · {availability.reason}. Checked {availability.checked_at ?? 'time not supplied'} · {availability.basis}</p>
          <details><summary>Advertised image times · {availability.times.length}</summary><p>{availability.times.length ? availability.times.join(', ') : 'No image times declared'}</p></details>
          <p>Run freshness assessed at: {layer.freshness_assessed_at ?? 'Not supplied'}</p>
          <p>Listed native frames: {layer.times?.length ? layer.times.join(', ') : 'None supplied; imagery availability is unknown'}</p><p>Actual drawn frames: {actual?.times.length ? actual.times.join(', ') : 'None'} · {actual?.description ?? 'No draw receipt'}</p>
          <button onClick={(event) => onInspect({ key: `layer:${layer.id}`, label: layer.title, text: actual?.description ?? 'Layer index only; no drawn frame confirmed', details: { 'Returned layer': layer, 'Actual draw': actual ?? null, 'Source mapping': mapping, 'Imagery availability': availability } }, event.currentTarget)}>Inspect layer record {layer.title}</button>
        </section>
      })}
    </details>
  </section>
}
function CoverageMarks({ values, instant }: { values: ServedFieldValue[]; instant: number }) {
  const plotted = values.filter((value) => value.attribution.validTime && Math.abs(Date.parse(value.attribution.validTime) - instant) <= 86400000)
  return <><svg className="source-coverage-marks" viewBox="0 0 720 64" role="img" aria-label={`${values.length} returned readings; exact native timestamps in the following disclosure`}>
    <path d="M20 24H700M360 12V38" stroke="currentColor" strokeDasharray="3 4" fill="none" />
    {plotted.map((value, index) => {
      const x = 20 + 680 * (Date.parse(value.attribution.validTime!) - instant + 86400000) / 172800000
      return value.hasValue && value.attribution.evidenceClass !== 'unrecognised' && !value.attribution.derivationRefused && !value.attribution.provenanceUnmodelled && !value.attribution.uncatalogued ? <circle className="native-samples" {...sourceAttributes(value.attribution.sourceId)} key={index} cx={x} cy="24" r="4" fill="currentColor" /> : <path className="native-samples" {...sourceAttributes(value.attribution.sourceId)} key={index} d={`M${x - 4} 20l8 8m0-8l-8 8`} stroke="currentColor" fill="none" />
    })}
    <text x="20" y="58">−24h</text><text x="342" y="58">Focus</text><text x="662" y="58">+24h</text>
  </svg>{values.length > plotted.length && <p>{values.length - plotted.length} readings have no in-range timestamp; see their individual provenance.</p>}
    <p>{[...new Set(values.map((value) => value.attribution.evidenceClass))].map((kind) => <span key={kind}><EvidenceGlyph kind={kind} />{kind} </span>)}</p>
  </>
}
