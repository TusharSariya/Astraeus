import { PrecipitationLegend, temperatureDescription } from './precipitationColours'
import { useEffect, useState } from 'react'
import { gridCell } from './sourceGrid'
import { ReturnedValue, readableGeometry } from './ReturnedValue'
import { SourceTag } from './SourceTag'
import type { GeoJsonFeature, LayerItem, LocationPoint, SourceStatusItem } from '../types'
import { stationCoverage, stations } from '../fixtures'
import { layerMapping, layerImagery } from './layerIdentity'
import { EvidenceGlyph, type InspectedEvidence } from './EvidenceInspector'
import type { DrawEvidence } from './MapStack'

export function mapLayerEvidence(id: string, layer: LayerItem | undefined, actual: DrawEvidence | undefined): InspectedEvidence {
  return { key: `layer:${id}`, label: layer?.title ?? actual?.title ?? id, text: actual?.description ?? 'No current draw receipt for this layer.', details: {
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
export const featureEvidenceKey = (row: DrawEvidence, index: number) => `map-feature:${JSON.stringify([row.id, row.selection, row.times, row.nativeGrid ? gridCell(row.nativeGrid,index) : row.features?.[index]])}`
export function openMapFeature(layer: string, index: number) {
  window.dispatchEvent(new CustomEvent('bench-grid-inspect',{detail:{layer,index}}))
  const control = document.getElementById(featureControlId(layer, index))
  if (!(control instanceof HTMLButtonElement)) return
  const disclosure = control.closest('details')
  if (disclosure) disclosure.open = true
  window.dispatchEvent(new Event('bench-map-evidence'))
  control.click()
}
function featureName(feature: GeoJsonFeature, index: number) {
  const properties = feature.properties ?? {}
  const name = properties.station_name ?? properties.station_id ?? properties.name ?? properties.identifier ?? properties.id
  return typeof name === 'string' || typeof name === 'number' ? String(name) : `Feature ${index + 1}`
}

/** Jump within the current Map without changing its shared Focus URL. */
export function MapSamplesLink() {
  return <a className="bench-map-samples-link" href="#bench-map-samples" onClick={(event) => {
    const heading = document.getElementById('bench-map-samples')
    const disclosure = heading?.closest('details')
    if (!heading || !disclosure) return
    event.preventDefault()
    disclosure.open = true
    heading.focus()
    heading.scrollIntoView({ block: 'nearest' })
  }}>Skip to Map samples</a>
}

/** Semantic counterpart of the actually displayed features, without a new acquisition. */
export function MapEvidenceDetails({ layers, drawn, location, instant, statuses, responseSourceIds, onSelect, onInspect }: {
  layers: LayerItem[]; drawn: DrawEvidence[]; location: LocationPoint; instant: number; statuses: SourceStatusItem[] | null; responseSourceIds: ReadonlySet<string>
  onSelect: (point: LocationPoint) => void; onInspect: (evidence: InspectedEvidence, opener: HTMLButtonElement) => void
}) {
  const [cell,setCell]=useState<{layer:string;index:number}|null>(null)
  useEffect(()=>{const listen=(event:Event)=>{setCell((event as CustomEvent).detail);window.dispatchEvent(new Event('bench-map-evidence'))};window.addEventListener('bench-grid-inspect',listen);return()=>window.removeEventListener('bench-grid-inspect',listen)},[])
  useEffect(() => {
    if (!cell) return
    const control = document.getElementById(featureControlId(cell.layer, cell.index))
    if (!(control instanceof HTMLButtonElement)) return
    const disclosure = control.closest('details')
    if (disclosure) disclosure.open = true
    control.click()
  }, [cell])
  const gridFeatures=drawn.filter(row=>row.drawn && row.nativeGrid && row.id===cell?.layer).flatMap(row=>cell!.index<row.nativeGrid!.latitudes.length*row.nativeGrid!.longitudes.length?[{row,feature:gridCell(row.nativeGrid!,cell!.index),index:cell!.index}]:[])
  const features = [...gridFeatures,...drawn.filter((row) => row.drawn).flatMap((row) => row.features?.map((feature, index) => ({ row, feature, index })) ?? [])]
  return <details className="bench-map-evidence"><summary>Map samples and display provenance · {features.length} returned features</summary>
    <h3 id="bench-map-samples" tabIndex={-1}>Map samples and display provenance</h3>
    <p>Focus {location.latitude}, {location.longitude} at {new Date(instant).toISOString()}. Raster images do not supply a numeric value at an arbitrary pixel. Feature properties below are exactly those returned for their own frame.</p>
    {drawn.filter(row=>row.drawn && row.nativeGrid).map(row=><p key={row.id}>{row.nativeGrid!.latitudes.length*row.nativeGrid!.longitudes.length} native cloud cells. Select a rectangle on the map to inspect it.</p>)}
    <table><caption>Displayed native features and station reports</caption><thead><tr><th scope="col">Feature / layer / source</th><th scope="col">Native frame / geometry</th><th scope="col">Returned properties</th><th scope="col">Provenance</th></tr></thead><tbody>
      {features.map(({ row, feature, index }) => {
        const layer = layers.find((entry) => entry.id === row.id), name = featureName(feature, index)
        const sources = layer ? [...new Set(layerMapping(layer).fields.map((field) => field.source_id))] : row.sourceId ? [row.sourceId] : []
        return <tr key={featureControlId(row.id, index)}><th scope="row"><EvidenceGlyph kind={row.evidenceClass ?? 'unrecognised'} />{name}<small>{layer?.title ?? row.title ?? row.id} · {sources.length ? sources.map((id) => <SourceTag key={id} id={id} />) : 'Source identity not supplied'} · {row.evidenceClass ?? 'unrecognised'}</small></th>
          <td>{row.times.join(', ') || 'Frame time not supplied'}<ReturnedValue value={readableGeometry(feature.geometry)} /></td>
          <td><ReturnedValue value={feature.properties} />{row.precipitation?.[index] && <><p>Temperature-based colours · {temperatureDescription(row.precipitation[index]!.temperature)}</p><PrecipitationLegend scale={row.precipitation[index]!.scale}/></>}</td>
          <td><button id={featureControlId(row.id, index)} onClick={(event) => onInspect({ key: featureEvidenceKey(row, index), label: `${name} · ${layer?.title ?? row.title ?? row.id}`, text: 'Returned native feature, not a sample of the raster at this pixel.', details: { 'Temperature-based colours': row.precipitation?.[index] ? {association:row.precipitation[index]!.sourceChoice ?? 'auto',temperature:temperatureDescription(row.precipitation[index]!.temperature),scale:row.precipitation[index]!.scale}:null, 'Native cell index': index, 'Returned feature properties': feature.properties, 'Native frame times': row.times, 'Returned feature geometry': feature.geometry, 'Map layer': row.id, 'Source/field mapping': layer ? layerMapping(layer) : null, 'Map draw description': row.description, 'Frame acquisition provenance':row.images } }, event.currentTarget)}>Inspect {name} from {layer?.title ?? row.title ?? row.id}</button></td></tr>
      })}
    </tbody></table>
    {!features.length && <p>No native feature values are currently drawn. An image, a reference marker or an empty feature response does not establish a point measurement.</p>}
    <h3>Display construction and real inputs</h3>
    {drawn.map((row) => <section key={row.id}><h4><EvidenceGlyph kind={row.evidenceClass ?? 'unrecognised'} />{layers.find((layer) => layer.id === row.id)?.title ?? row.title ?? row.id}</h4><p>{row.description}</p>
      <p>{row.display?.kind ?? 'No construction receipt'} · Actual inputs: {row.times.join(', ') || 'None drawn'}. Method version: {row.display?.methodVersion ?? 'Not supplied'}. Capture identity: {row.display?.captureIdentity ?? 'Not supplied'}.</p>
      <button onClick={(event) => onInspect(mapLayerEvidence(row.id, layers.find((layer) => layer.id === row.id), row), event.currentTarget)}>Inspect actual display {layers.find((layer) => layer.id === row.id)?.title ?? row.title ?? row.id}</button></section>)}
    <h3>Reference location markers</h3>
    <p>These are the existing location pickers. They are distinct from returned station reports; selecting one changes Focus and does not create station evidence.</p>
    <ul>{stations.map((point) => { const coverage = stationCoverage(point, statuses, responseSourceIds); return <li key={point.id}><strong>{point.name}</strong><p>{coverage.detail}</p>
      <button onClick={() => onSelect(point)}>Use {point.name} as Focus</button><button onClick={(event) => onInspect({ key: `map-location:${point.id}`, label: point.name, text: coverage.detail, details: { 'Reference location': point, 'Declared source identities': point.sourceIds ?? [], 'Coverage scope': coverage, 'Selected Focus': location, 'Selected instant': new Date(instant).toISOString() } }, event.currentTarget)}>Inspect reference location {point.name}</button>
    </li> })}</ul>
  </details>
}
