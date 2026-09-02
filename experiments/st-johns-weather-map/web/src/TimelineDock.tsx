/** The always-visible timeline dock under the map: scrubber, published-frame
 *  markers, playback transport, quick jumps, the valid-instant badge, the
 *  display-interpolation toggle and the story panel toggle. Presentational —
 *  every behaviour is the caller's handler, so the snap rules and the
 *  playback clock live in one place (App) for both this and the expert
 *  slider. */

import { useEffect, useMemo, useRef, useState } from 'react'
import { stJohnsTime, type FrameMarkers, type InterpolationMethodItem } from './api'
import { CoveragePanel } from './CoveragePanel'
import { MethodMenu } from './MethodMenu'
import { describeSpeed, PLAYBACK_SPEEDS, type PlaybackDirection, type PlaybackSpeed } from './playback'
import { placeScaleMarks, textMeasurer } from './scrubberAxis'
import { boundaryMark, HORIZON_SCALE_MARKS, planningTierHasCoverage } from './tierBoundary'
import type { TimelineResponse } from './types'

export interface TimelineDockProps {
  offsetMinutes: number
  scrubOffset: string
  /** The effective selected instant on the St. John's clock. */
  validClock: string
  backMinutes: number
  forwardMinutes: number
  /** True when scrub actions snap to the union of active layers' frames. */
  snapping: boolean
  ariaValueText: string
  onScrubMinutes: (rawMinutes: number) => void
  onScrubKeyDown: (event: React.KeyboardEvent<HTMLInputElement>) => void
  onQuickJump: (offsetHours: number) => void
  /** The window the scrubber spans, for placing the frame markers on the
   *  same scale as the slider. */
  windowStartMs: number
  windowEndMs: number
  /** Exactly the frames the active layers published — never a tick for an
   *  instant nothing published. */
  markers: FrameMarkers
  onJumpToInstant: (ms: number) => void
  playing: boolean
  speed: PlaybackSpeed
  direction: PlaybackDirection
  onTogglePlay: () => void
  onFaster: () => void
  onSlower: () => void
  onToggleDirection: () => void
  interpolate: boolean
  onToggleInterpolate: () => void
  /** The interpolation bench, exactly as the server publishes it, plus the
   *  method currently drawn. Offered next to the interpolation toggle because
   *  it settles the same question: what is shown between two real frames. */
  methods: InterpolationMethodItem[]
  method: string
  onSelectMethod: (methodId: string) => void
  methodNotices: string[]
  methodError: string | null
  storyOpen: boolean
  onToggleStory: () => void
  storyToggleRef: React.RefObject<HTMLButtonElement | null>
  /** The `/timeline` response, exactly as loaded, plus its own error — for
   *  the boundary marker, the no-planning-frames note and the per-instant
   *  coverage panel (tasks 4.1, 4.2). Null timeline falls back to the fixed
   *  window and draws no boundary tick, since a mark implies a stated fact. */
  timeline: TimelineResponse | null
  timelineError: string | null
  selectedMs: number
}

const QUICK_JUMPS = [-3, -1, 0, 3, 6, 12, 18, 24]

/** The thumb width the slider draws, so a marker at the same instant sits
 *  under the thumb's centre rather than drifting toward the ends. */
const THUMB_PX = 18

export function TimelineDock({
  offsetMinutes, scrubOffset, validClock, backMinutes, forwardMinutes, snapping, ariaValueText,
  onScrubMinutes, onScrubKeyDown, onQuickJump, windowStartMs, windowEndMs, markers, onJumpToInstant,
  playing, speed, direction, onTogglePlay, onFaster, onSlower, onToggleDirection,
  interpolate, onToggleInterpolate,
  methods, method, onSelectMethod, methodNotices, methodError,
  storyOpen, onToggleStory, storyToggleRef,
  timeline, timelineError, selectedMs,
}: TimelineDockProps) {
  const span = windowEndMs - windowStartMs
  const boundary = useMemo(
    () => boundaryMark(timeline?.boundary ?? null, timeline?.tiers ?? null, windowStartMs, windowEndMs),
    [timeline, windowStartMs, windowEndMs],
  )
  const planningHasFrames = useMemo(
    () => planningTierHasCoverage(timeline?.items ?? [], timeline?.boundary ?? null),
    [timeline],
  )
  // The rail the scale labels are placed on, measured rather than assumed:
  // the same viewport can give it very different widths depending on whether
  // the conditions strip sits beside it.
  const labelsRef = useRef<HTMLDivElement | null>(null)
  const [railPx, setRailPx] = useState(0)
  const [labelFont, setLabelFont] = useState('')
  useEffect(() => {
    const element = labelsRef.current
    if (!element) return
    const read = () => {
      setRailPx(element.getBoundingClientRect().width)
      const style = getComputedStyle(element)
      setLabelFont(`${style.fontWeight} ${style.fontSize} ${style.fontFamily}`)
    }
    read()
    if (typeof ResizeObserver !== 'function') return
    const observer = new ResizeObserver(read)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  // `text-transform: uppercase` is what is actually painted, so that is what
  // is measured. The face is monospaced, so this only matters if it ever
  // stops being.
  const scaleMarks = useMemo(() => placeScaleMarks({
    marks: HORIZON_SCALE_MARKS,
    backMinutes,
    forwardMinutes,
    railPx,
    measure: textMeasurer(labelFont, (text) => text.toUpperCase()),
  }), [backMinutes, forwardMinutes, railPx, labelFont])
  // One swatch per layer that actually has a tick on the rail, in the order
  // the markers carry (which is the retrieved layer order).
  const key = new Map<string, { title: string; color: string }>()
  for (const marker of markers.markers) {
    for (const layer of marker.layers) if (!key.has(layer.id)) key.set(layer.id, { title: layer.title, color: layer.color })
  }
  // Tracks each layer's most recently seen run as the marker rail is walked
  // in ascending time order (which `markers.markers` already is), so a
  // change point can be detected instant by instant without re-scanning.
  const lastRunByLayer = new Map<string, string | null>()
  return (
    <section className="timeline-dock" aria-label="Scrub timeline">
      <div className="timeline-dock-head">
        <div className="story-scrubber-badge">
          <span>Valid:</span>
          <strong>{offsetMinutes === 0 ? `Now (0h) · ${validClock} NT` : `${scrubOffset} (${offsetMinutes < 0 ? 'Past' : 'Forecast'}) · ${validClock} NT`}</strong>
        </div>
        <CoveragePanel timeline={timeline} timelineError={timelineError} selectedMs={selectedMs} />
        {/* Always in the layout so its appearance never rewraps the head row
            and resizes the dock (and with it the map) mid-scrub. */}
        <small className={`dock-snap-note ${snapping ? '' : 'idle'}`} aria-hidden={!snapping}>
          snapped to the nearest published frame of the active layers
        </small>
        <button
          type="button"
          className={`dock-toggle ${interpolate ? 'on' : ''}`}
          aria-pressed={interpolate}
          onClick={onToggleInterpolate}
          title="Interpolates forecast imagery between two real frames for display — advection-corrected along a derived motion field where one exists, a linear cross-dissolve otherwise. Never applied to observed layers; not evidence."
        >
          Interpolate forecast · display only
        </button>
        {interpolate && methods.length > 0 && (
          <MethodMenu
            methods={methods}
            active={method}
            onSelect={onSelectMethod}
            notices={methodNotices}
            error={methodError}
          />
        )}
        <button
          type="button"
          ref={storyToggleRef}
          className={`dock-toggle ${storyOpen ? 'on' : ''}`}
          aria-expanded={storyOpen}
          aria-controls="story-flyout"
          onClick={onToggleStory}
        >
          Weather story {storyOpen ? '▾' : '▴'}
        </button>
      </div>
      <div className="timeline-scrubber-controls">
        <div className="scrubber-bar-wrapper">
          <div className="scrubber-labels" ref={labelsRef}>
            {scaleMarks.map(({ hours, text, fraction, anchor }) => (
              <span
                key={hours}
                className={`scrubber-mark ${anchor === 'center' ? '' : anchor} ${hours === 0 ? 'scrubber-now' : ''}`}
                style={{ left: `${fraction * 100}%` }}
              >
                {text}
              </span>
            ))}
            {/* The 24 h core/planning boundary: a tick plus a label, not
                colour alone, with a visually-hidden text alternative naming
                both tier ranges (task 4.1). Drawn only when `/timeline`
                declared one — an older API gets no guessed boundary. */}
            {boundary && (
              <span
                className="scrubber-mark boundary-mark"
                style={{ left: `${Math.min(1, Math.max(0, boundary.fraction)) * 100}%` }}
                aria-describedby="tier-boundary-description"
              >
                {boundary.label}
              </span>
            )}
          </div>
          {boundary && <p id="tier-boundary-description" className="visually-hidden">{boundary.description}</p>}
          <input
            aria-label="Valid timeline scrubber"
            aria-valuetext={ariaValueText}
            type="range"
            min={-backMinutes}
            max={forwardMinutes}
            step={1}
            value={offsetMinutes}
            onChange={(event) => onScrubMinutes(Number(event.target.value))}
            onKeyDown={onScrubKeyDown}
            className="timeline-slider"
          />
          <div className="frame-marker-rail" role="group" aria-label="Published frames">
            {markers.markers.map((marker) => {
              const fraction = span > 0 ? (marker.ms - windowStartMs) / span : 0
              if (fraction < 0 || fraction > 1) return null
              const colors = marker.layers.map(({ color }) => color)
              // A frame two layers share is ONE tick split between their
              // colours, never two ticks stacked and one of them unclickable.
              const background = colors.length === 1
                ? colors[0]
                : `linear-gradient(180deg, ${colors.map((color, index) => `${color} ${(index / colors.length) * 100}%, ${color} ${((index + 1) / colors.length) * 100}%`).join(', ')})`
              const clock = stJohnsTime(marker.time)
              // Each layer's own run, where it declared one, alongside its
              // title — the segment label task 4.3 asks for, kept in the
              // title/aria text of the existing tick rather than a second
              // widget. A layer whose `frames[]` never declared a run at all
              // is named without one; a declared-but-unknown run says so.
              const titles = marker.layers.map(({ title, runTime }) => {
                if (runTime === undefined) return title
                return runTime === null ? `${title} (run unknown)` : `${title} (run ${runTime})`
              }).join(', ')
              // The change point this task asks the rail to mark: any layer
              // at this instant whose declared run differs from the one it
              // carried at the previous instant it published.
              const changed = marker.layers.some(({ id, runTime }) => {
                if (runTime === undefined) return false
                const previous = lastRunByLayer.get(id)
                lastRunByLayer.set(id, runTime)
                return previous !== undefined && previous !== runTime
              })
              return (
                <button
                  key={marker.ms}
                  type="button"
                  className={`frame-marker ${changed ? 'frame-marker-run-change' : ''}`}
                  style={{ left: `calc(${fraction * 100}% + ${(0.5 - fraction) * THUMB_PX}px)`, background }}
                  title={`Published frame · ${clock} NT · ${titles}${changed ? ' · run changed here' : ''}`}
                  aria-label={`Published frame — ${titles}, ${clock} NT${changed ? ', run changed here' : ''}`}
                  onClick={() => onJumpToInstant(marker.ms)}
                />
              )
            })}
          </div>
          <div className="frame-marker-key">
            {[...key.values()].map(({ title, color }) => (
              <span key={title} className="marker-key-entry">
                <i style={{ background: color }} aria-hidden="true" />
                {title}
              </span>
            ))}
            {markers.markers.length === 0 && <span className="marker-key-note">No active layer published a frame in this window</span>}
            {markers.axisless.length > 0 && <span className="marker-key-note">No published frame axis: {markers.axisless.join(', ')}</span>}
          </div>
          {/* When nothing retrieved past the boundary covers any instant, the
              planning side says so plainly rather than drawing an axis that
              implies coverage it does not have (task 4.1). */}
          {boundary && !planningHasFrames && (
            <p className="marker-key-note planning-tier-empty">planning tier holds no published frames</p>
          )}
        </div>
        <div className="scrubber-transport-row">
          <div className="timeline-transport" role="group" aria-label="Timeline playback">
            <button
              type="button"
              className="transport-button"
              onClick={onSlower}
              disabled={speed === PLAYBACK_SPEEDS[0]}
              aria-label="Slower"
              title="Halve the playback speed"
            >⏴⏴</button>
            <button
              type="button"
              className={`transport-button play ${playing ? 'on' : ''}`}
              onClick={onTogglePlay}
              aria-pressed={playing}
              aria-label={playing ? 'Pause' : 'Play'}
              title={playing ? 'Pause' : 'Play the timeline'}
            >{playing ? '⏸' : '▶'}</button>
            <button
              type="button"
              className="transport-button"
              onClick={onFaster}
              disabled={speed === PLAYBACK_SPEEDS[PLAYBACK_SPEEDS.length - 1]}
              aria-label="Faster"
              title="Double the playback speed"
            >⏵⏵</button>
            <button
              type="button"
              className={`transport-button ${direction === -1 ? 'on' : ''}`}
              onClick={onToggleDirection}
              aria-pressed={direction === -1}
              aria-label="Reverse"
              title="Play backwards"
            >⇄</button>
            <span className="transport-speed" aria-live="off">
              {direction === -1 ? '◀ ' : ''}{describeSpeed(speed, 1)}
            </span>
            <span className="visually-hidden" aria-live="polite">{playing ? `Playing at ${describeSpeed(speed, direction)}` : 'Paused'}</span>
          </div>
          <div className="scrubber-quick-jumps">
            {QUICK_JUMPS.map((offset) => (
              <button key={offset} type="button" className={offsetMinutes === offset * 60 ? 'active' : ''} onClick={() => onQuickJump(offset)}>
                {offset === 0 ? 'Now' : offset > 0 ? `+${offset}h` : `${offset}h`}
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
