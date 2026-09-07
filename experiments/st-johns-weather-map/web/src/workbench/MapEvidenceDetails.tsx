import type { GeoJsonFeature, LayerItem, LocationPoint, SourceStatusItem } from '../types'
import { stationCoverage, stations } from '../fixtures'
import { layerMapping, layerImagery } from './layerIdentity'
import { EvidenceGlyph, type InspectedEvidence } from './EvidenceInspector'
import type { DrawEvidence } from './MapStack'

export function mapLayerEvidence(id: string, layer: LayerItem | undefined, actual: DrawEvidence | undefined): InspectedEvidence {
  return { key: `layer:${id}`, label: layer?.title ?? id, text: actual?.description ?? 'No current draw receipt for this layer.', details: {
    'Returned layer': layer ?? null, 'Actual draw': actual ?? null,
    'Source/field mapping': layer ? layerMapping(layer) : null,
    'Imagery availability': layer ? layerImagery(layer) : null,
    'Actual frame times': actual?.times ?? [],
    'Display construction': actual?.display ?? null,
    'Returned image provenance': actual?.images ?? null,
    'Capture identity': actual?.display?.captureIdentity ?? null,
    'Method version': actual?.display?.methodVersion ?? null,
    'Run freshness assessed at': layer?.freshness_assessed_at ?? null,
  } }
}
export const featureControlId = (layer: string, index: number) => `map-feature-${encodeURIComponent(layer)}-${index}`
export const featureEvidenceKey = (row: DrawEvidence, index: number) => `map-feature:${JSON.stringify([row.id, row.selection, row.times, row.features?.[index]])}`
export function openMapFeature(layer: string, index: number) {
  const control = document.getElementById(featureControlId(layer, index))
  if (!(control instanceof HTMLButtonElement)) return
  const disclosure = control.closest('details')
  if (disclosure) disclosure.open = true
  control.click()
}
function featureName(feature: GeoJsonFeature, index: number) {
  const properties = feature.properties ?? {}
  const name = properties.station_name ?? properties.station_id ?? properties.name ?? properties.identifier ?? properties.id
  return typeof name === 'string' || typeof name === 'number' ? String(name) : `Feature ${index + 1}`
}

/** Semantic counterpart of the actually displayed features, without a new acquisition. */
export function MapEvidenceDetails({ layers, drawn, location, instant, statuses, responseSourceIds, onSelect, onInspect }: {
  layers: LayerItem[]; drawn: DrawEvidence[]; location: LocationPoint; instant: number; statuses: SourceStatusItem[] | null; responseSourceIds: ReadonlySet<string>
  onSelect: (point: LocationPoint) => void; onInspect: (evidence: InspectedEvidence, opener: HTMLButtonElement) => void
}) {
  const features = drawn.filter((row) => row.drawn).flatMap((row) => row.features?.map((feature, index) => ({ row, feature, index })) ?? [])
  return <details className="bench-map-evidence"><summary>Map samples and display provenance · {features.length} returned features</summary>
    <p>Focus {location.latitude}, {location.longitude} at {new Date(instant).toISOString()}. Raster images do not supply a numeric value at an arbitrary pixel. Feature properties below are exactly those returned for their own frame.</p>
    <table><caption>Displayed native features and station reports</caption><thead><tr><th scope="col">Feature / layer / source</th><th scope="col">Native frame / geometry</th><th scope="col">Returned properties</th><th scope="col">Provenance</th></tr></thead><tbody>
      {features.map(({ row, feature, index }) => {
        const layer = layers.find((entry) => entry.id === row.id), name = featureName(feature, index)
        const sources = layer ? [...new Set(layerMapping(layer).fields.map((field) => field.source_id))] : []
        return <tr key={featureControlId(row.id, index)}><th scope="row"><EvidenceGlyph kind={row.evidenceClass ?? 'unrecognised'} />{name}<small>{layer?.title ?? row.id} · {sources.join(', ') || 'Source identity not supplied'} · {row.evidenceClass ?? 'unrecognised'}</small></th>
          <td>{row.times.join(', ') || 'Frame time not supplied'}<pre>{JSON.stringify(feature.geometry, null, 2)}</pre></td>
          <td><pre>{JSON.stringify(feature.properties, null, 2)}</pre></td>
          <td><button id={featureControlId(row.id, index)} onClick={(event) => onInspect({ key: featureEvidenceKey(row, index), label: `${name} · ${layer?.title ?? row.id}`, text: 'Returned native feature, not a sample of the raster at this pixel.', details: { 'Map layer': row.id, 'Native frame times': row.times, 'Source/field mapping': layer ? layerMapping(layer) : null, 'Returned feature geometry': feature.geometry, 'Returned feature properties': feature.properties, 'Map draw description': row.description } }, event.currentTarget)}>Inspect {name} from {layer?.title ?? row.id}</button></td></tr>
      })}
    </tbody></table>
    {!features.length && <p>No native feature values are currently drawn. An image, a reference marker or an empty feature response does not establish a point measurement.</p>}
    <h3>Display construction and real inputs</h3>
    {drawn.map((row) => <section key={row.id}><h4><EvidenceGlyph kind={row.evidenceClass ?? 'unrecognised'} />{layers.find((layer) => layer.id === row.id)?.title ?? row.id}</h4><p>{row.description}</p>
      <p>{row.display?.kind ?? 'No construction receipt'} · Actual inputs: {row.times.join(', ') || 'None drawn'}. Method version: {row.display?.methodVersion ?? 'Not supplied'}. Capture identity: {row.display?.captureIdentity ?? 'Not supplied'}.</p>
      <button onClick={(event) => onInspect(mapLayerEvidence(row.id, layers.find((layer) => layer.id === row.id), row), event.currentTarget)}>Inspect actual display {layers.find((layer) => layer.id === row.id)?.title ?? row.id}</button></section>)}
    <h3>Reference location markers</h3>
    <p>These are the existing location pickers. They are distinct from returned station reports; selecting one changes Focus and does not create station evidence.</p>
    <ul>{stations.map((point) => { const coverage = stationCoverage(point, statuses, responseSourceIds); return <li key={point.id}><strong>{point.name}</strong><p>{coverage.detail}</p>
      <button onClick={() => onSelect(point)}>Use {point.name} as Focus</button><button onClick={(event) => onInspect({ key: `map-location:${point.id}`, label: point.name, text: coverage.detail, details: { 'Reference location': point, 'Declared source identities': point.sourceIds ?? [], 'Coverage scope': coverage, 'Selected Focus': location, 'Selected instant': new Date(instant).toISOString() } }, event.currentTarget)}>Inspect reference location {point.name}</button>
    </li> })}</ul>
  </details>
}
