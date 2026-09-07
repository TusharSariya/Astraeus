import { useState } from 'react'
import type { CatalogSource, LayerItem, ServedFieldValue, SourceStatusItem } from '../types'
import { familyTitle, fieldDefinition } from '../fieldFamily'
import { EvidenceGlyph, EvidenceLedger, type InspectedEvidence } from './EvidenceInspector'
import type { DrawEvidence } from './MapStack'

interface Props {
  catalog: CatalogSource[]; statuses: SourceStatusItem[] | null; fields: ServedFieldValue[]; layers: LayerItem[]; drawn: DrawEvidence[]
  instant: number; catalogError: string | null; statusError: string | null
  onInspect: (evidence: InspectedEvidence, opener: HTMLButtonElement) => void
}
export function sourceEvidence(id: string, catalog: CatalogSource[], statuses: SourceStatusItem[] | null, fields: ServedFieldValue[]): InspectedEvidence {
  return { key: `source:${id}`, label: id, text: 'Registry declaration, acquisition status and returned point evidence have separate scopes.', details: {
    'Source identity': id,
    'Registry declaration': catalog.find((source) => source.id === id) ?? 'Not present in the returned catalogue',
    'Acquisition status': statuses?.find((status) => status.source_id === id) ?? 'Not supplied; successful point retrieval is not inferred',
    'Returned evidence at Focus': fields.filter((field) => field.attribution.sourceId === id).map((field) => ({ field: field.field, text: field.text, has_value: field.hasValue, provenance: field.attribution.responseProvenance })),
    'Coverage limitation': 'Declared geography, a retrieval timestamp or a layer listing does not establish availability at this coordinate and time.',
  } }
}
/** State lives with App, preserving filters and selection across stage/dock changes. */
export function useSourcesView(props: Props) {
  const [perspective, setPerspective] = useState('Ledger')
  const [query, setQuery] = useState('')
  const [family, setFamily] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const { catalog, statuses, fields, layers, drawn, instant, onInspect } = props
  const allIds = [...new Set([...catalog.map((source) => source.id), ...fields.flatMap((field) => field.attribution.sourceId ? [field.attribution.sourceId] : []), ...(statuses ?? []).map((status) => status.source_id)])]
  const families = [...new Set([...catalog.flatMap((source) => source.fields?.map((field) => field.family) ?? []), ...fields.map((field) => field.attribution.family)].filter((value): value is string => typeof value === 'string' && value.length > 0))].sort()
  const visible = allIds.filter((id) => {
    const source = catalog.find((entry) => entry.id === id)
    const values = fields.filter((field) => field.attribution.sourceId === id)
    return [id, source?.producer, source?.product, ...source?.fields?.map((field) => field.key) ?? []].join(' ').toLowerCase().includes(query.trim().toLowerCase())
      && (!family || source?.fields?.some((field) => field.family === family) || values.some((field) => field.attribution.family === family))
  })
  function inspect(id: string, opener: HTMLButtonElement) { setSelected(id); onInspect(sourceEvidence(id, catalog, statuses, fields), opener) }
  const inspectButton = (id: string) => <button aria-pressed={selected === id} onClick={(event) => inspect(id, event.currentTarget)}>Inspect source {id}</button>
  const readings = (id: string) => fields.filter((field) => field.attribution.sourceId === id && (!family || field.attribution.family === family))
  return <section className="sources-view" aria-label="Source evidence catalogue">
    <div className="sources-controls"><div role="group" aria-label="Sources perspective">{['Ledger', 'Family finder', 'Coverage lanes'].map((name) => <button key={name} aria-pressed={perspective === name} onClick={() => setPerspective(name)}>{name}</button>)}</div>
      <label>Find source or field<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
      <label>Field family<select value={family} onChange={(event) => setFamily(event.target.value)}><option value="">All families</option>{families.map((name) => <option key={name} value={name}>{familyTitle(name)}</option>)}</select></label>
      <button onClick={() => { setQuery(''); setFamily('') }}>Clear filters</button>
    </div>
    <p>Declared capability, successful acquisition and evidence at Focus are separate facts. Native samples and listed frames do not imply continuous or geographic coverage.</p>
    {props.catalogError && <p>Catalogue unreadable: {props.catalogError}</p>}{props.statusError && <p>Acquisition status unreadable: {props.statusError}</p>}
    <p>{visible.length} sources match. {selected && <>Inspected source: {selected}{!visible.includes(selected) && ' (outside the current filters)'}</>}</p>
    {perspective === 'Ledger' && <div className="sources-table"><table><caption>Source Ledger at the shared Focus</caption><thead><tr><th scope="col">Source</th><th scope="col">Declared capability</th><th scope="col">Acquisition report</th><th scope="col">Returned point evidence</th><th scope="col">Provenance</th></tr></thead><tbody>
      {visible.map((id) => {
        const source = catalog.find((entry) => entry.id === id), status = statuses?.find((entry) => entry.source_id === id), values = readings(id)
        return <tr key={id} data-selected={selected === id}><th scope="row">{id}<small>{source?.producer ?? 'Producer not declared'} · {source?.product ?? 'Product not declared'}</small></th>
          <td>{source?.state ?? 'Registry state unknown'}<small>{source?.status_reason}</small><small>{source?.geographic_coverage ?? 'Geography not declared'}</small><small>{source?.fields ? `${source.fields.length} declared fields` : 'Fields not declared'}</small></td>
          <td>{status ? `${status.state} · ${status.data_mode}` : 'Acquisition status unknown'}<small>{status?.last_retrieval ? `Reported retrieval ${status.last_retrieval}` : 'No retrieval time supplied'}</small><small>{status?.detail}</small></td>
          <td>{values.length ? `${values.length} returned readings; inspect their individual availability` : 'No readings returned at Focus; coverage unestablished'}</td><td>{inspectButton(id)}</td></tr>
      })}
    </tbody></table></div>}
    {perspective === 'Family finder' && <div>{(family ? [family] : families).map((name) => {
      const declarations = visible.flatMap((id) => catalog.find((source) => source.id === id)?.fields?.filter((field) => field.family === name).map((field) => ({ id, field })) ?? [])
      return <section className="source-family-card" key={name}><h3>{familyTitle(name)}</h3>{declarations.length === 0 && <p>No matching field declaration was returned.</p>}
        <ul>{declarations.map(({ id, field }) => <li key={`${id}:${field.key}`}><strong>{field.key}</strong> · {id}<p>{fieldDefinition(field.key)}</p><p>Declared storage: {field.storage ?? 'unknown'} · Native field: {field.upstream ?? 'not supplied'}</p>{field.note && <p>{field.note}</p>}{inspectButton(id)}</li>)}</ul>
      </section>
    })}</div>}
    {perspective === 'Coverage lanes' && <div><p>Each marker is a returned native timestamp, within 24 hours either side of Focus. Unmarked spans are unqueried. × means a returned reading is absent or withheld, not an all-clear.</p>
      {visible.map((id) => <section className="source-coverage-lane" key={id}><h3>{id}</h3><CoverageMarks values={readings(id)} instant={instant} />
        {readings(id).length === 0 && <p>No point samples were returned. Declared horizon and retrieval status do not fill this lane.</p>}
        {inspectButton(id)}<details><summary>Native values and absence states · {readings(id).length} readings</summary><EvidenceLedger rows={readings(id)} onInspect={onInspect} /></details>
      </section>)}
    </div>}
    {selected && perspective !== 'Coverage lanes' && <details className="source-selected-values"><summary>Returned values from {selected}</summary><EvidenceLedger rows={readings(selected)} onInspect={onInspect} /></details>}
    <details className="sources-unmapped"><summary>Layer frame identities · {layers.length} layers</summary><p>The layer API does not yet supply explicit source-to-field joins. These records stay separate from source coverage; no join is inferred from a title or product.</p>
      {layers.filter((layer) => `${layer.id} ${layer.title}`.toLowerCase().includes(query.toLowerCase())).map((layer) => {
        const actual = drawn.find((entry) => entry.id === layer.id)
        return <section key={layer.id}><h3>{layer.title}</h3><p>Layer {layer.id} · Source mapping unknown · Field {layer.field_key ?? 'not supplied'}</p>
          <p>Listed native frames: {layer.times?.length ? layer.times.join(', ') : 'None supplied; imagery availability is unknown'}</p><p>Actual drawn frames: {actual?.times.length ? actual.times.join(', ') : 'None'} · {actual?.description ?? 'No draw receipt'}</p>
          <button onClick={(event) => onInspect({ key: `layer:${layer.id}`, label: layer.title, text: actual?.description ?? 'Layer index only; no drawn frame confirmed', details: { 'Returned layer': layer, 'Actual draw': actual ?? null, 'Source mapping': 'Unknown' } }, event.currentTarget)}>Inspect layer record {layer.title}</button>
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
      return value.hasValue && value.attribution.evidenceClass !== 'unrecognised' && !value.attribution.derivationRefused && !value.attribution.provenanceUnmodelled && !value.attribution.uncatalogued ? <circle key={index} cx={x} cy="24" r="4" fill="currentColor" /> : <path key={index} d={`M${x - 4} 20l8 8m0-8l-8 8`} stroke="currentColor" fill="none" />
    })}
    <text x="20" y="58">−24h</text><text x="342" y="58">Focus</text><text x="662" y="58">+24h</text>
  </svg>{values.length > plotted.length && <p>{values.length - plotted.length} readings have no in-range timestamp; see their individual provenance.</p>}
    <p>{[...new Set(values.map((value) => value.attribution.evidenceClass))].map((kind) => <span key={kind}><EvidenceGlyph kind={kind} />{kind} </span>)}</p>
  </>
}
