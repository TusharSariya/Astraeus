import { ReturnedValue, readableGeometry } from './ReturnedValue'
import { SourceTag } from './SourceTag'
import { useEffect, useRef } from 'react'
import { EVIDENCE_CLASS_LABELS } from '../evidenceClass'
import type { FieldAttribution, ResolvedEvidenceClass, ServedFieldValue } from '../types'

export interface InspectedEvidence { key: string; label: string; text: string; attribution?: FieldAttribution; details?: Record<string, unknown> }
export function EvidenceGlyph({ kind }: { kind: ResolvedEvidenceClass }) {
  const diamond = kind === 'derived_here' || kind === 'intermediary_derived'
  return <svg className={`bench-glyph class-${kind}`} width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
    {kind === 'unrecognised' ? <path d="M2 2L14 14M14 2L2 14" fill="none" stroke="currentColor" strokeWidth="2" />
      : diamond ? <path d="M8 1L15 8L8 15L1 8Z" stroke="currentColor" strokeWidth="1.8" fill={kind === 'derived_here' ? 'currentColor' : 'none'} />
      : <rect x="2" y="2" width="12" height="12" rx={kind === 'uncalibrated_observation' ? 6 : 0} stroke="currentColor" strokeWidth="1.8" strokeDasharray={kind === 'generated_display' ? '3 2' : undefined} fill={kind === 'retrieved' ? 'currentColor' : 'none'} />}
  </svg>
}
export function evidenceKey(row: ServedFieldValue): string {
  const a = row.attribution
  const native = a.responseProvenance?.native_report
  const report = native && typeof native === 'object' && !Array.isArray(native) ? native as Record<string, unknown> : {}
  return `value:${JSON.stringify([row.field, a.sourceId, a.fieldKey, a.member, a.phase, a.validTime, a.runTime, report.station_id, report.provider_report_id])}`
}
export function EvidenceLedger({ rows, onInspect }: { rows: ServedFieldValue[]; onInspect: (evidence: InspectedEvidence, opener: HTMLButtonElement) => void }) {
  return <table className="bench-ledger"><caption>Evidence at Focus · native values and returned identity</caption>
    <thead><tr><th scope="col">Class</th><th scope="col">Field / source</th><th scope="col">Value</th><th scope="col">Provenance</th></tr></thead>
    <tbody>{rows.map((row, index) => {
      const a = row.attribution
      const refused = a.evidenceClass === 'unrecognised' || a.derivationRefused || a.provenanceUnmodelled || a.uncatalogued
      const text = refused ? 'Unavailable' : row.text
      return <tr key={`${evidenceKey(row)}:${index}`}>
        <td><EvidenceGlyph kind={a.evidenceClass} /><span>{EVIDENCE_CLASS_LABELS[a.evidenceClass]}</span></td>
        <th scope="row">{row.field}<small><SourceTag id={a.sourceId} /></small><small>{a.validTime ?? 'Native time not supplied'}</small></th>
        <td>{row.hasValue && !refused ? text : '—'}<small>{!row.hasValue || refused ? a.notice ?? (a.qualityFlags.join(', ') || 'Value not supplied') : row.units}</small></td>
        <td><button onClick={(event) => onInspect({ key: evidenceKey(row), label: row.field, text, attribution: a }, event.currentTarget)} aria-label={`Inspect ${row.field} from ${a.sourceId ?? 'unknown source'} at ${a.validTime ?? 'unknown native time'}${a.runTime ? `, run ${a.runTime}` : ''}`}>Inspect</button></td>
      </tr>
    })}</tbody>
  </table>
}
const show = (value: unknown): string => value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0) ? 'Not supplied' : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)
export function EvidenceInspector({ evidence, onClose }: { evidence: InspectedEvidence; onClose: () => void }) {
  const heading = useRef<HTMLHeadingElement | null>(null)
  useEffect(() => { heading.current?.focus() }, [evidence.key])
  const a = evidence.attribution
  const nativeFeature = evidence.key.startsWith('map-feature:')
  return <aside className="bench-companion bench-inspector" aria-label="Evidence inspector" onKeyDown={(event) => {
    if (event.key === 'Escape' && !(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLSelectElement)) { event.stopPropagation(); event.preventDefault(); onClose() }
  }}>
    <div className="bench-view-heading"><h2 ref={heading} tabIndex={-1}>Evidence · {evidence.label}</h2><button onClick={onClose}>Close inspector</button></div>
    <p>{evidence.text}</p>
    <dl>{Object.entries(a ? {
      Class: EVIDENCE_CLASS_LABELS[a.evidenceClass], Source: a.sourceId, Producer: a.provider, Product: a.product,
      'Delivery kind': a.deliveryKind, Intermediary: a.intermediary, 'Native valid time': a.validTime,
      Run: a.runTime, 'Capture revision': a.artifactRevision, 'Catalogue field': a.fieldKey,
      Absence: a.notice, Quality: a.qualityStatus, 'Quality flags': a.qualityFlags,
      'Last valid time': a.lastValidTime, Method: a.derivationMethod, Inputs: a.derivationInputs,
      'Method sentence': a.derivation, 'Method version': a.derivationVersion,
      Member: a.member, Ensemble: a.ensemble, Phase: a.phase,
      'Sample geometry': ['sampled_latitude', 'sampled_longitude', 'sample_distance_km', 'sample_method'].some((key) => a.responseProvenance?.[key] != null) ? { latitude: a.responseProvenance?.sampled_latitude ?? null, longitude: a.responseProvenance?.sampled_longitude ?? null, distance_km: a.responseProvenance?.sample_distance_km ?? null, method: a.responseProvenance?.sample_method ?? null } : null, 'Freshness assessment': a.responseProvenance?.freshness, Terms: a.responseProvenance?.licence,
      'Complete returned provenance': a.responseProvenance,
      ...evidence.details,
    } : evidence.details ?? { Provenance: null }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{nativeFeature ? <ReturnedValue value={label === 'Returned feature geometry' ? readableGeometry(value) : value} /> : show(value)}</dd></div>)}</dl>
    {nativeFeature && evidence.details?.['Returned feature properties'] !== undefined && <details><summary>Complete returned Map record · JSON</summary><pre>{JSON.stringify(evidence.details, null, 2)}</pre></details>}
  </aside>
}
