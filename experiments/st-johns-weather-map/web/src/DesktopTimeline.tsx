import { useEffect, useMemo, useRef, useState } from 'react'
import { frameMarkers, resolveLayerFrame, drawableFrames, describeResolution, layerGroup, LAYER_GROUP_LABELS, type FrameMarker } from './api'
import type { LayerItem, LayerSelection } from './types'
import type { DrawEvidence } from './workbench/MapStack'
import type { TimelineDockProps } from './TimelineDock'
import { CoveragePanel, resolveCoverageState, timelineItemForInstant } from './CoveragePanel'
import { MethodMenu } from './MethodMenu'
import { PLAYBACK_SPEEDS, type PlaybackSpeed } from './playback'
import { clusterMarkers, frameNeighbour, frameTime, markerDescription, rangeMarks, TIME_RANGES, type TimeRange } from './timelineModel'
import { placeScaleMarks, textMeasurer } from './scrubberAxis'

export interface DesktopTimelineOptions {
  range: TimeRange; onRange: (range: TimeRange) => void
  onInterval: (interval: PlaybackSpeed) => void
  onStep: (direction: 1 | -1) => void; onFrame: (direction: 1 | -1) => void
  onReveal: () => void
  layers: LayerItem[]; selections: LayerSelection[]; drawn: DrawEvidence[]; reference: Date
  evidenceStartMs: number; evidenceEndMs: number
  expanded: boolean; onExpanded: (open: boolean) => void
}
function useRail() {
  const ref = useRef<HTMLDivElement>(null)
  const [geometry, setGeometry] = useState({ width: 800, font: '11px monospace' })
  useEffect(() => {
    const node = ref.current
    if (!node) return
    const measure = () => {
      const style = getComputedStyle(node)
      setGeometry({ width: node.getBoundingClientRect().width, font: `${style.fontWeight} ${style.fontSize} ${style.fontFamily}` })
    }
    measure()
    if (typeof ResizeObserver !== 'function') return
    const observer = new ResizeObserver(measure); observer.observe(node)
    return () => observer.disconnect()
  }, [])
  return { ref, ...geometry }
}
function FrameRail({ markers, start, end, selected, onPick, label, layers, onCluster }: {
  markers: FrameMarker[]; start: number; end: number; selected: number; onPick: (ms: number) => void
  label: string; layers: LayerItem[]; onCluster: (markers: FrameMarker[], opener: HTMLButtonElement) => void
}) {
  const { ref, width } = useRail()
  const [hint, setHint] = useState<string | null>(null)
  const clusters = clusterMarkers(markers, start, end, width)
  const changes = new Set<number>(); const runs = new Map<string, string | null>()
  for (const marker of markers) for (const layer of marker.layers) {
    if (layer.runTime === undefined) continue
    if (runs.has(layer.id) && runs.get(layer.id) !== layer.runTime) changes.add(marker.ms)
    runs.set(layer.id, layer.runTime)
  }
  return <div ref={ref} className="native-frame-rail" role="group" aria-label={label}>
    {clusters.map(cluster => {
      const first = cluster.markers[0]; const count = cluster.markers.length
      const text = count > 1 ? `${count} frame times · ${frameTime(first.ms)} to ${frameTime(cluster.markers[count - 1].ms)}` : markerDescription(first)
      const changed = cluster.markers.some(marker => changes.has(marker.ms))
      const forecast = first.layers.some(entry => {
        const layer = layers.find(item => item.id === entry.id)
        return layer && ['forecast_proxy', 'published_model'].includes(layerGroup(layer))
      })
      const observed = first.layers.every(entry => { const layer = layers.find(item => item.id === entry.id); return layer && ['satellite', 'observation'].includes(layerGroup(layer)) })
      return <button key={first.ms} className={`native-frame-marker${count > 1 ? ' clustered' : ''}${changed ? ' run-change' : ''}`}
        style={{ left: `${cluster.fraction * 100}%` }} aria-label={`${text}${changed ? ' · run change' : ''}`}
        aria-pressed={cluster.markers.some(marker => marker.ms === selected)} title={text}
        onMouseEnter={() => setHint(text)} onMouseLeave={() => setHint(null)} onFocus={() => setHint(text)} onBlur={() => setHint(null)}
        onClick={event => { setHint(null); if (count > 1) onCluster(cluster.markers, event.currentTarget); else onPick(first.ms) }}>
        {count > 1 ? count : forecast ? '◇' : observed ? '│' : '?'}<span className="native-source-swatches" aria-hidden="true">{first.layers.map(layer => <i key={layer.id} style={{ background:layer.color }} />)}</span>{changed && <span className="native-run-flag" aria-hidden="true">↯</span>}
      </button>
    })}
    {selected >= start && selected <= end && end > start && <span className="native-playhead" style={{ left: `${(selected-start)/(end-start)*100}%` }} aria-hidden="true" />}
    {hint && <div role="tooltip" className="native-frame-hint">{hint}</div>}
  </div>
}

export function DesktopTimeline(props: TimelineDockProps & { desktop: DesktopTimelineOptions }) {
  const { desktop: state, selectedMs, windowStartMs: start, windowEndMs: end, markers, timeline, timelineError } = props
  const { ref, width, font } = useRail()
  const [chooser, setChooser] = useState<FrameMarker[] | null>(null)
  useEffect(() => {
    const close = () => setChooser(null)
    window.addEventListener('bench-timeline-dismiss', close)
    return () => window.removeEventListener('bench-timeline-dismiss', close)
  }, [])
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const opener = useRef<HTMLButtonElement | null>(null)
  const tracksButton = useRef<HTMLButtonElement>(null)
  const chooserHeading = useRef<HTMLHeadingElement>(null)
  const tracksHeading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { if (chooser) chooserHeading.current?.focus() }, [chooser])
  useEffect(() => { if (state.expanded) tracksHeading.current?.focus() }, [state.expanded])
  useEffect(() => { setChooser(null); setPage(0) }, [state.range])
  const coverage = resolveCoverageState(timeline, timelineError, timeline ? timelineItemForInstant(timeline.items, selectedMs) : null)
  const coverageText = coverage.kind === 'entries' ? `${coverage.entries.length} covering sources` : coverage.kind === 'empty' ? 'Nothing covers this instant' : 'Coverage unavailable'
  const candidates = rangeMarks(state.range, start, end, state.reference.getTime()).map(mark => mark.hours === 24 && timeline?.boundary ? { ...mark, label: '+24h | planning', short: '+24h | planning' } : mark)
  const labels = placeScaleMarks({ marks: candidates, backMinutes: props.backMinutes, forwardMinutes: props.forwardMinutes, railPx: width, measure: textMeasurer(font) })
  const instants = markers.markers.map(marker => marker.ms)
  const offscreen = selectedMs < start || selectedMs > end
  const outsideWindow = selectedMs < state.evidenceStartMs || selectedMs > state.evidenceEndMs
  const boundary = timeline?.boundary ? Date.parse(timeline.boundary) : NaN
  const rows = useMemo(() => [...state.selections].reverse().map(selection => {
    const layer = state.layers.find(layer => layer.id === selection.id)
    return { selection, layer, markers: layer ? frameMarkers(state.layers, [{ id: layer.id, visible: true }], start, end).markers : [] }
  }), [state.layers, state.selections, start, end])
  const allFrames = rows.flatMap(row => row.markers)
  const filteredFrames = (chooser ?? allFrames).filter(marker => markerDescription(marker).toLowerCase().includes(query.toLowerCase())).sort((a,b) => a.ms - b.ms)
  const pages = Math.max(1, Math.ceil(filteredFrames.length / 50))
  const currentPage = Math.min(page, pages - 1)
  const closeChooser = () => { setChooser(null); setQuery(''); setPage(0); (opener.current?.isConnected ? opener.current : tracksButton.current)?.focus() }
  const closeTracks = () => { state.onExpanded(false); tracksButton.current?.focus() }
  const pick = (ms: number) => { props.onJumpToInstant(ms); if (chooser) closeChooser() }
  const openCluster = (frames: FrameMarker[], button: HTMLButtonElement) => { window.dispatchEvent(new Event('bench-timeline-activate')); opener.current = button; setQuery(''); setPage(0); setChooser(frames) }
  const frameList = <>
    <label className="timeline-search">Search frame timestamps or layers<input type="search" value={query} onChange={event => { setQuery(event.target.value); setPage(0) }} /></label>
    <p>{filteredFrames.length} native frame entries · published availability, not proof of retrieval</p>
    <ol className="timeline-frame-list">{filteredFrames.slice(currentPage*50, currentPage*50+50).map((marker,index) => <li key={`${marker.ms}-${index}`}><button onClick={() => pick(marker.ms)}>{markerDescription(marker)}</button></li>)}</ol>
    {!filteredFrames.length && <p>No matching published frames.</p>}
    {pages > 1 && <div className="timeline-pagination"><button disabled={currentPage === 0} onClick={() => setPage(currentPage-1)}>Previous timestamps</button><span>Page {currentPage+1} of {pages}</span><button disabled={currentPage+1 >= pages} onClick={() => setPage(currentPage+1)}>Next timestamps</button></div>}
  </>
  return <div className="bench-time-control" onKeyDown={event => {
    if (event.key !== 'Escape' || event.defaultPrevented) return
    if (chooser) { event.preventDefault(); event.stopPropagation(); closeChooser() }
    else if (state.expanded) { event.preventDefault(); event.stopPropagation(); closeTracks() }
  }}>
    <div className="bench-time-slim">
      <div className="timeline-main-controls" role="group" aria-label="Timeline playback">
        <button aria-label="Previous frame" disabled={frameNeighbour(instants, selectedMs, -1) === null} onClick={() => state.onFrame(-1)} title="Previous native frame">│◀</button>
        <button aria-label={`Step backward ${props.speed} minutes`} onClick={() => state.onStep(-1)} title={`Back ${props.speed} minutes`}>−{props.speed}m</button>
        <button aria-label={props.playing ? 'Pause' : 'Play'} aria-pressed={props.playing} onClick={props.onTogglePlay}>{props.playing ? 'Ⅱ' : '▶'}</button>
        <button aria-label={`Step forward ${props.speed} minutes`} onClick={() => state.onStep(1)} title={`Forward ${props.speed} minutes`}>+{props.speed}m</button>
        <button aria-label="Next frame" disabled={frameNeighbour(instants, selectedMs, 1) === null} onClick={() => state.onFrame(1)} title="Next native frame">▶│</button>
        <label className="timeline-interval"><span className="visually-hidden">Step and playback interval</span><select value={props.speed} onChange={event => { const value = PLAYBACK_SPEEDS.find(value => value === Number(event.target.value)); if (value) state.onInterval(value) }}>{PLAYBACK_SPEEDS.map(value => <option key={value} value={value}>{value} min</option>)}</select></label>
        <button aria-label="Reverse" aria-pressed={props.direction === -1} onClick={props.onToggleDirection} title="Reverse playback">⇄</button>
        <div className="bench-time-selected"><strong><time dateTime={new Date(selectedMs).toISOString()}>{frameTime(selectedMs)}</time></strong><small>{props.playing ? `${props.direction === -1 ? 'Reverse · ' : ''}${props.speed} min each second` : 'Paused'} · {props.scrubOffset}</small></div>
        <button onClick={() => props.onJumpToInstant(state.reference.getTime())}>Now</button>
        <label><span className="visually-hidden">Timeline range</span><select aria-label="Timeline range" value={state.range} onChange={event => { const value = TIME_RANGES.find(value => value.id === event.target.value); if (value) state.onRange(value.id) }}>{TIME_RANGES.map(range => <option key={range.id} value={range.id}>{range.label}</option>)}</select></label>
        <button ref={node => { tracksButton.current = node; props.storyToggleRef.current = node }} aria-expanded={state.expanded} aria-controls="timeline-tracks" onClick={() => { if (state.expanded) closeTracks(); else state.onExpanded(true) }}>Tracks</button>
      </div>
      <div className="timeline-compact-axis">
        <div className="timeline-axis-status" title={coverage.kind === 'unavailable' ? coverage.reason : coverageText}>{outsideWindow ? <span>Selected time outside timeline window</span> : offscreen ? <button onClick={state.onReveal}>Selected time {selectedMs < start ? '← before' : 'after →'} range</button> : <><span>{coverageText}</span><small>{markers.markers.length ? `${markers.markers.length} native times` : 'No published frames in range'}</small></>}</div>
        <div className="timeline-axis-geometry">
          <div className="timeline-scale" ref={ref}>{labels.map(mark => <span key={mark.hours} className={`scrubber-mark ${mark.anchor}`} style={{ left: `${mark.fraction*100}%` }}>{mark.text}</span>)}</div>
          <input className="timeline-compact-slider" aria-label="Valid timeline scrubber" aria-valuetext={props.ariaValueText} type="range" min={-props.backMinutes} max={props.forwardMinutes} step="any" value={Math.max(-props.backMinutes, Math.min(props.forwardMinutes, (selectedMs-state.reference.getTime())/60_000))} onChange={event => props.onScrubMinutes(Number(event.target.value))} onKeyDown={props.onScrubKeyDown} />
          <FrameRail markers={markers.markers} start={start} end={end} selected={selectedMs} label="Published frames" onPick={pick} layers={state.layers} onCluster={openCluster} />
        </div>
      </div>
    </div>
    {state.expanded && <section id="timeline-tracks" className="bench-time-expanded" aria-label="Layer timeline tracks">
      <div className="timeline-tracks-head"><h2 ref={tracksHeading} tabIndex={-1}>Native frame tracks</h2><button onClick={closeTracks}>Close tracks</button></div>
      <p>Drawing order · top first. │ Observations · ◇ Forecasts · ? Other/unknown · ↯ Run change. Markers describe published availability; drawn times below come from map receipts.</p>
      {Number.isFinite(boundary) && boundary >= start && boundary <= end && <p>Core through +24h; planning to +14d. Gaps indicate no reported frames.</p>}
      <div className="timeline-track-rows">{rows.map(({ selection, layer, markers: native }) => {
        if (!layer) return <article key={selection.id}><strong>{selection.id}</strong><p>Layer unavailable · no published frame axis</p></article>
        const resolution = resolveLayerFrame(layer, new Date(selectedMs), { reference: state.reference, interpolate: props.interpolate && layer.evidence_basis !== 'demand_query' })
        const frames = drawableFrames(resolution)
        const receipt = state.drawn.find(row => row.id === layer.id)
        const shownTimes = receipt?.drawn ? receipt.times : frames.map(frame => frame.time)
        const runFlags = shownTimes.map(time => layer.frames?.find(frame => Date.parse(frame.valid_time) === Date.parse(time))?.run_stale)
        const runStatus = runFlags.some(flag => flag === true) ? 'Stale run' : runFlags.length && runFlags.every(flag => flag === false) ? 'Run within cadence' : 'Run freshness unknown'
        const provider = [...new Set(layer.field_mappings?.map(mapping => mapping.source_id) ?? [])].join(', ') || `${layer.product} · provider unknown`
        return <article className={`timeline-track${selection.visible ? '' : ' is-hidden'}`} key={selection.id}>
          <div className="timeline-track-title"><strong title={layer.title}>{layer.title}</strong><span>{selection.visible ? LAYER_GROUP_LABELS[layerGroup(layer)] : 'Hidden'} · {provider} · {layer.cadence_seconds ? `${layer.cadence_seconds/60} min cadence` : 'Cadence unknown'}</span></div>
          <FrameRail markers={native} start={start} end={end} selected={selectedMs} onPick={pick} layers={[layer]} onCluster={openCluster} label={`${layer.title} frames`} />
          {!native.length && <p>{layer.times?.length ? 'No published frames in this range' : 'No published frame axis'}</p>}
          <div className="timeline-track-status"><span>{!selection.visible ? 'Hidden · excluded from navigation' : receipt?.status ?? (receipt?.drawn ? 'drawn' : 'Map receipt unavailable')} · {receipt?.drawn ? `Drawn ${receipt.times.map(time => frameTime(Date.parse(time))).join(' + ')}` : frames.length ? `Native ${frames.map(frame => frameTime(Date.parse(frame.time))).join(' + ')}` : 'No eligible frame'} · {runStatus}{receipt?.evidenceClass === 'generated_display' ? ' · GENERATED display' : ''}</span>
          <details><summary>Frame details</summary><p>{describeResolution(resolution) ?? 'Exact native frame'}.</p><p>{receipt?.description ?? 'Map receipt unavailable for this selection.'}</p><p>Declared run: {frames.map(frame => layer.frames?.find(entry => entry.valid_time === frame.time)?.run_time ?? 'unknown').join(', ') || 'unknown'}. {layer.run_stale_reason}</p></details></div>
        </article>
      })}</div>
      {!rows.length && <p>No active layers. Add layers to see their native timelines.</p>}
      <details><summary>Frame timestamp list</summary>{!chooser && frameList}</details>
      <details><summary>Coverage and display settings</summary><CoveragePanel timeline={timeline} timelineError={timelineError} selectedMs={selectedMs} />
        {Number.isFinite(boundary) && !timeline?.items.some(item => Date.parse(item.valid_time_utc) > boundary && item.coverage?.length) && <p>Planning tier holds no reported coverage.</p>}
        <button aria-pressed={props.interpolate} onClick={props.onToggleInterpolate}>Interpolate forecast · display only</button>
        {props.interpolate && props.methods.length > 0 && <MethodMenu methods={props.methods} active={props.method} onSelect={props.onSelectMethod} notices={props.methodNotices} error={props.methodError} />}
      </details>
      <button aria-expanded={props.storyOpen} onClick={props.onToggleStory}>Weather story</button>
    </section>}
    {chooser && <section className="timeline-frame-chooser" role="dialog" aria-label="Choose a native frame">
      <div className="timeline-tracks-head"><h2 ref={chooserHeading} tabIndex={-1}>Choose a native frame</h2><button onClick={closeChooser}>Close frame chooser</button></div>{frameList}
    </section>}
  </div>
}
