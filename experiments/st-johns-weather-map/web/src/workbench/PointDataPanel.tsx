import { useLoadedTemperatures, temperatureSample, temperatureFor, valueTarget, temperatureDescription, precipitationScale, precipitationColour, PrecipitationLegend } from './precipitationColours'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { CatalogSource, LayerItem, LayerSelection, LocationPoint, PointFieldSelection, ServedFieldValue } from '../types'
import { familyTitle } from '../fieldFamily'
import { mapOnlyLayer, selectionPoints, pointIdentity, pointFamily, pointLabel, pointFieldLabel, pointUnavailable, matchesPoint, variantIdentity } from './pointSelections'
import { pointRequest, usePointRequests } from './pointRequests'
import { EvidenceInspector, type InspectedEvidence } from './EvidenceInspector'
import type { DrawEvidence } from './MapStack'
import { mapLayerEvidence } from './MapEvidenceDetails'

const UNAVAILABLE = 'point-unavailable'
export function relativeValidTime(validTime: string | null | undefined, clock: number) {
  const stamp = validTime ? Date.parse(validTime) : NaN
  if (!Number.isFinite(stamp)) return 'Time unknown'
  const minutes = Math.round(Math.abs(stamp - clock) / 60000)
  if (minutes === 0) return 'now'
  const label = minutes < 60 ? `${minutes} min` : minutes < 1440 ? `${Math.round(minutes / 60)} h` : `${Math.round(minutes / 1440)} d`
  return stamp > clock ? `in ${label}` : `${label} ago`
}
export function compactValue(value: ServedFieldValue) {
  if (value.attribution.fieldKey === 'radar_echo' && value.value === 0) return '0 · no echo'
  if (value.value !== null && ['%', 'percent', 'percentage'].includes(value.units ?? '')) return `${Number(value.value.toFixed(1))}%`
  return value.text
}
export function concisePointReason(reason: string) {
  if (reason === 'Image only') return reason
  if (/credentials|permission|401|403/i.test(reason)) return 'Credentials required'
  if (/selection unavailable/i.test(reason)) return 'Native time unavailable'
  if (/capability|unsupported/i.test(reason)) return 'Point unsupported'
  if (/outside.*(?:area|coverage)/i.test(reason)) return 'Outside coverage'
  if (/quality check failed/i.test(reason)) return 'Quality check failed'
  if (/source unavailable|fail|error|timeout|timed out|API returned (?:5[0-9]{2}|429)/i.test(reason)) return 'Source unavailable'
  return 'No reading at selected time'
}
const PREFERENCE = 'astraeus-point-data-minimized'
const readMinimized = () => { try { return localStorage.getItem(PREFERENCE) === 'true' } catch { return false } }
export function openPointData(id: string) { window.dispatchEvent(new CustomEvent('bench-open-point-data', { detail: id })) }
interface SelectedReading { key: string; owners: string[]; label: string; family: string; point?: PointFieldSelection; layerId?: string }
export function selectedReadings(stack: LayerSelection[], layers: LayerItem[], catalog: CatalogSource[]) {
  const rows = new Map<string, SelectedReading>()
  for (const entry of stack) {
    const points = selectionPoints(entry, layers, catalog)
    if (!points.length) {
      const layer = layers.find(l => l.id === entry.id)
      if (mapOnlyLayer(layer, catalog)) continue
      rows.set(entry.id, { key: entry.id, owners: [entry.id], label: layer?.title ?? entry.id, family: layer?.family ?? 'ungrouped', layerId: entry.id })
    }
    for (const point of points) {
      const key = `${pointIdentity(point)}:${variantIdentity(point.variant)}:${point.level}`
      const existing = rows.get(key)
      if (existing) existing.owners.push(entry.id)
      else rows.set(key, { key, owners: [entry.id], label: pointLabel(point), family: pointFamily(point, catalog), point })
    }
  }
  return [...rows.values()]
}
function valueAllowed(row: ServedFieldValue) {
  const a = row.attribution
  return row.hasValue && a.qualityStatus !== 'failed' && a.evidenceClass !== 'unrecognised' && !a.derivationRefused && !a.provenanceUnmodelled && !a.uncatalogued
}
export function PointDataPanel({ stack, layers, catalog, location, instant, drawn, runs = {}, focusReady = true }: {
  stack: LayerSelection[]; layers: LayerItem[]; catalog: CatalogSource[]; location: LocationPoint; instant: number; drawn: DrawEvidence[]; runs?: Record<string, string>; focusReady?: boolean
}) {
  const rows = useMemo(() => selectedReadings(stack, layers, catalog), [stack, layers, catalog])
  const requests = rows.flatMap(row => row.point && focusReady && !pointUnavailable(row.point, catalog, runs) ? [pointRequest(location, instant, row.point)] : [])
  const results = usePointRequests(requests)
  const {publish} = useLoadedTemperatures()
  const temperatureSamples = useMemo(() => Object.values(results).flatMap(state => state.result?.source !== 'fixture' ? state.result?.snapshot.servedFields.flatMap(v => {const t=temperatureSample(v,location.latitude,location.longitude);return t?[t]:[]}) ?? [] : []), [results,location.latitude,location.longitude])
  useEffect(() => {publish({latitude:location.latitude,longitude:location.longitude,instant,samples:temperatureSamples})},[publish,temperatureSamples,location.latitude,location.longitude,instant])
  const temperatureChoice = (owners:string[])=>stack.find(s=>owners.includes(s.id))?.temperatureSource ?? 'auto'
  const [clock, setClock] = useState(Date.now)
  useEffect(() => { const timer = setInterval(() => setClock(Date.now()), 60000); return () => clearInterval(timer) }, [])
  const [minimized, setMinimized] = useState(readMinimized)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [target, setTarget] = useState<string | null>(null)
  const [detail, setDetail] = useState<{key: string; opener: HTMLButtonElement; scroll: number} | null>(null)
  const root = useRef<HTMLElement>(null), contents = useRef<HTMLDivElement>(null), toggle = useRef<HTMLButtonElement>(null)
  const focused = useRef<{key:string; node:HTMLButtonElement} | null>(null)
  const buttons = useRef(new Map<string, HTMLButtonElement>())
  const setPreference = (value: boolean) => { setMinimized(value); try { localStorage.setItem(PREFERENCE, String(value)) } catch { /* Preference still works in this session. */ } }
  useEffect(() => {
    const open = (event: Event) => { setPreference(false); setDetail(null); setTarget((event as CustomEvent<string>).detail) }
    window.addEventListener('bench-open-point-data', open)
    return () => window.removeEventListener('bench-open-point-data', open)
  }, [])
  useLayoutEffect(() => {
    const node = root.current
    if (!node) return
    const measure = () => node.closest<HTMLElement>('.bench')?.style.setProperty('--point-panel-height', `${node.getBoundingClientRect().height}px`)
    measure()
    if (typeof ResizeObserver !== 'function') return
    const observer = new ResizeObserver(measure); observer.observe(node)
    return () => observer.disconnect()
  }, [])
  const closeDetail = () => {
    const back = detail; setDetail(null)
    const group = resolved.find(value => value.row.key === back?.key)?.group
    if (group) setCollapsed(current => { const next = new Set(current); next.delete(group); return next })
    requestAnimationFrame(() => { if (contents.current && back) contents.current.scrollTop = back.scroll; (back ? buttons.current.get(back.key) ?? toggle.current : toggle.current)?.focus({preventScroll:true}) })
  }
  const minimize = () => { setDetail(null); setPreference(true); requestAnimationFrame(() => toggle.current?.focus()) }
  const resolved = rows.map(row => {
    const p = row.point
    const state = p ? results[pointRequest(location, instant, p).key] : undefined
    const unavailable = p ? !focusReady ? 'Resolving selected location…' : pointUnavailable(p, catalog, runs) : null
    const values = p && !unavailable && state?.result?.source !== 'fixture' ? state?.result?.snapshot.servedFields.filter(value => matchesPoint(value, p)) ?? [] : []
    const frame = drawn.find(d => d.id === row.layerId)
    const failure = state?.error ?? state?.result?.error
    const accessFailure = failure && /\b(401|403)\b/.test(failure) ? `Credentials or access permission required. ${failure}` : failure
    const imageOnly = ['satellite_natural_color','satellite_dayvis_nightir','satellite_snowfog_nightmicro','satellite_nightir'].includes(layers.find(layer => layer.id === row.layerId)?.field ?? '')
    const status = !p ? imageOnly ? 'Image only' : 'Point capability unavailable' : unavailable ?? accessFailure ?? (state?.result?.source === 'fixture' ? 'Development fixture is not current point evidence.' : null) ?? (state ? (values.length ? null : 'No selected field returned at this native time.') : 'Loading…')
    const evidence: InspectedEvidence = p ? { key:`point:${row.key}`, label:row.label,
      text: status ?? values.map(v => valueAllowed(v) ? v.text : v.attribution.notice ?? (v.attribution.qualityFlags.join(', ') || 'Value unavailable')).join('; '),
      attribution: values.length === 1 ? values[0].attribution : undefined,
      details: { 'Selected location': {latitude:location.latitude,longitude:location.longitude}, 'Selected time':new Date(instant).toISOString(), 'Point product':p.product, 'Time selection policy':'directional',
        'Selected level':p.level ?? 'Not selected', 'Selected member / statistic':p.variant ?? 'Not selected',
        'Returned native time': values.map(v => v.attribution.validTime),
        'Offset seconds': values.map(v => v.attribution.validTime ? (Date.parse(v.attribution.validTime)-instant)/1000 : null),
        'Temperature-based colours':values.filter(v=>precipitationScale(v.attribution.fieldKey ?? v.field,v.units)).map(v=>({association:temperatureChoice(row.owners)==='auto'?'Same source → HRDPS':temperatureChoice(row.owners),temperature:temperatureDescription(temperatureFor(valueTarget(v,location.latitude,location.longitude),temperatureSamples,runs['eccc-hrdps'],Date.now(),temperatureChoice(row.owners)))})),
        'Returned readings':values.map(v => ({field:v.field,value:valueAllowed(v) ? v.text : null,units:v.units,provenance:v.attribution.responseProvenance})),
        'Response notices':state?.result?.snapshot.notices ?? [], Availability:status } }
      : { ...mapLayerEvidence(row.layerId!, layers.find(l => l.id === row.layerId), frame), text:`Numeric point values unavailable. ${frame?.description ?? 'No frame drawn.'}` }
    const usable = values.filter(valueAllowed)
    const loading = !!p && (!focusReady || !unavailable && !state)
    const omitted = !loading && !usable.length
    const reason = status ?? values[0]?.attribution.notice ?? (values[0]?.attribution.qualityStatus === 'failed' ? 'Quality check failed' : 'No reading at selected time')
    return {row,values:usable,status,evidence,frame,loading,omitted,reason,group:omitted ? UNAVAILABLE : row.family}
  })
  useLayoutEffect(() => {
    if (!target || minimized) return
    const reading = resolved.find(value => value.row.owners.includes(target))
    const row = reading?.row
    if (!row) return
    if (collapsed.has(reading!.group)) { setCollapsed(current => { const next = new Set(current); next.delete(reading!.group); return next }); return }
    const button = buttons.current.get(row.key)
    if (button) { button.focus({preventScroll:true}); button.scrollIntoView?.({block:'nearest'}); setTarget(null) }
  }, [target, minimized, rows, collapsed, results])
  useLayoutEffect(() => {
    const previous = focused.current
    if (detail || minimized || !previous || previous.node.isConnected || document.activeElement !== document.body) return
    const reading = resolved.find(value => value.row.key === previous.key)
    if (!reading) { focused.current = null; toggle.current?.focus({preventScroll:true}); return }
    if (collapsed.has(reading.group)) {
      setCollapsed(current => { const next = new Set(current); next.delete(reading.group); return next })
    } else buttons.current.get(previous.key)?.focus({preventScroll:true})
  })
  const activeDetail = resolved.find(value => value.row.key === detail?.key)
  return <aside ref={root} className={`point-data-panel${minimized ? ' is-minimized' : ''}`} aria-label="Point data" onKeyDown={event => {
    if (event.key !== 'Escape' || event.defaultPrevented) return
    event.preventDefault(); event.stopPropagation()
    if (detail) closeDetail(); else minimize()
  }}>
    <header className="point-data-heading"><div><h2>Point data</h2>{minimized ? <small>{rows.length} selected {rows.length === 1 ? 'field' : 'fields'}</small> : <small title={`${location.name} · ${location.latitude}, ${location.longitude} · ${new Date(instant).toISOString()}`}>{location.name} · {location.latitude.toFixed(3)}, {location.longitude.toFixed(3)}<br /><time dateTime={new Date(instant).toISOString()}>{new Date(instant).toISOString().replace('T',' ').replace('.000Z',' UTC')}</time></small>}</div>
      <button ref={toggle} aria-label={minimized ? 'Expand Point data' : 'Minimize Point data'} aria-expanded={!minimized} onClick={() => minimized ? setPreference(false) : minimize()}>{minimized ? 'Expand' : 'Minimize'}</button>
    </header>
    <div ref={contents} className="point-data-contents" hidden={minimized}>
      <div hidden={!!detail}>
        {!rows.length && <p>Select fields in Layers to see point data at this location and time.</p>}
        {[...new Set(resolved.filter(value => !value.omitted).map(value => value.group)), ...(resolved.some(value => value.omitted) ? [UNAVAILABLE] : [])].map(family => <section key={family} className="point-data-category">
          <h3><button aria-expanded={!collapsed.has(family)} onClick={() => setCollapsed(current => { const next = new Set(current); if (next.has(family)) next.delete(family); else next.add(family); return next })}>{collapsed.has(family) ? '▸' : '▾'} {family === UNAVAILABLE ? `Point data not available (${resolved.filter(value => value.omitted).length})` : familyTitle(family)}</button></h3>
          <ul hidden={collapsed.has(family)}>{resolved.filter(value => value.group === family).map(({row, values, loading, omitted, reason}) => {
            const ambiguous = rows.filter(other => other.family === row.family && other.point?.sourceId === row.point?.sourceId).length > 1 || (catalog.find(source => source.id === row.point?.sourceId)?.fields?.filter(field => field.family === row.family).length ?? 0) > 1
            const levelAmbiguous = rows.some(other => other.point?.sourceId === row.point?.sourceId && other.point?.field === row.point?.field && other.point?.level !== row.point?.level)
            const productAmbiguous = rows.some(other => other.point?.sourceId === row.point?.sourceId && other.point?.productId !== row.point?.productId)
            const qualifier = row.point ? [productAmbiguous ? row.point.productId : null, ambiguous && !(row.point.field === 'radar_echo' && values[0]?.value === 0) ? pointFieldLabel(row.point) : null, row.point.field.startsWith('weathernext3_') ? null : row.point.variant?.statistic, levelAmbiguous ? row.point.level : null].filter(Boolean).join(' · ') : ''
            return <li key={row.key}>
              <button className={`point-data-reading${omitted ? ' point-data-omitted' : ''}`} ref={node => { if (node) buttons.current.set(row.key,node); else buttons.current.delete(row.key) }} onFocus={event => { focused.current = {key:row.key,node:event.currentTarget} }} onBlur={() => { focused.current = null }} aria-label={`Details for point reading ${row.label}`} aria-description={[row.point?.sourceId, ...values.map(v => `${compactValue(v)} · ${v.attribution.validTime ?? 'Native time not supplied'}`), omitted ? reason : null].filter(Boolean).join('. ')} onClick={event => { setDetail({key:row.key,opener:event.currentTarget,scroll:contents.current?.scrollTop ?? 0}); if(contents.current) contents.current.scrollTop = 0 }}>
                {omitted ? <><span>{row.point ? [row.point.sourceId,pointFieldLabel(row.point),row.point.variant?.member ? `Member ${row.point.variant.member}` : row.point.variant?.statistic].filter(Boolean).join(' · ') : row.label}</span><small title={reason}>{concisePointReason(reason)}</small></> : (values.length ? values : [null]).map((value,index) => <span className="point-data-line" key={index}>
                  <span className="point-data-source">{row.point?.sourceId === 'google-weathernext-3-statistics' ? 'weathernext-3' : row.point?.sourceId}<small>{[qualifier,value?.attribution.member ? `Member ${value.attribution.member}` : row.point?.variant?.member && row.point.variant.member !== 'all' ? `Member ${row.point.variant.member}` : null].filter(Boolean).join(' · ')}</small></span>
                  <span className="point-data-value">{value && (()=>{const scale=precipitationScale(value.attribution.fieldKey ?? value.field,value.units);if(!scale)return null;const t=temperatureFor(valueTarget(value,location.latitude,location.longitude),temperatureSamples,runs['eccc-hrdps'],Date.now(),temperatureChoice(row.owners));return <span title={`Temperature-based colours · ${temperatureDescription(t)}`} aria-label={`Temperature-based colours · ${temperatureDescription(t)}`} style={{display:'inline-block',width:10,height:10,border:'1px solid currentColor',marginRight:4,background:`rgba(${precipitationColour(value.value,t?.celsius??null,scale).slice(0,3).join(',')},${value.value===0?0:1})`}}/>})()}{value ? compactValue(value) : loading ? 'Loading…' : '—'}</span>
                  <time dateTime={value?.attribution.validTime ?? undefined}>{value ? relativeValidTime(value.attribution.validTime,clock) : ''}</time>
                </span>)}
              </button>
            </li>
          })}</ul>
        </section>)}
      </div>
      {detail && activeDetail?.values.map(v=>{const scale=precipitationScale(v.attribution.fieldKey ?? v.field,v.units);return scale?<PrecipitationLegend key={v.field} scale={scale}/>:null})}
      {detail && <EvidenceInspector preventFocusScroll evidence={activeDetail?.evidence ?? {key:detail.key,label:'Retained reading',text:'This reading is no longer selected.'}} onClose={closeDetail} />}
    </div>
  </aside>
}
