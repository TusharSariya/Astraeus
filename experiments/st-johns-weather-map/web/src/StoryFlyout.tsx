import { useEffect, useRef } from 'react'
import { describeOffset, groupLayers, nlTime, reading, resolveLayerFrame } from './api'
import type { FrameResolution } from './api'
import { ModeChip } from './ModeChip'
import type { AstronomyInterval, AstronomyResponse, LayerItem, LayerSelection, StoryStep } from './types'

/** The weather story and frame coverage, expanded over the map from the
 *  timeline dock. Everything here existed in the old below-the-fold story
 *  section; only its container moved. Nothing is interpolated between cards
 *  and no band is drawn from a failure. */

/** Text alternative for a coverage row, so the ribbon is not graphics-only. */
function coverageDescription(layer: LayerItem, frameCount: number, resolution: FrameResolution): string {
  if (frameCount === 0) return `${layer.title} published no frames in this window.`
  const where = resolution.kind === 'exact'
    ? `the selected time resolves to a frame ${describeOffset(resolution.frame.offsetSeconds)}`
    : resolution.kind === 'snapped'
      ? `the selected time falls back to a frame ${describeOffset(resolution.frame.offsetSeconds)}, disclosed on the map`
      : resolution.kind === 'blend'
        ? 'the selected time is drawn as a disclosed display composite of the two neighbouring frames'
        : `the selected time has no drawable frame: ${resolution.reason}`
  return `${layer.title}: ${frameCount} published frame${frameCount === 1 ? '' : 's'}; ${where}.`
}

function ribbonLabel(frameCount: number, resolution: FrameResolution): string {
  if (frameCount === 0) return 'no frames'
  if (resolution.kind === 'exact') return describeOffset(resolution.frame.offsetSeconds)
  if (resolution.kind === 'snapped') return `${describeOffset(resolution.frame.offsetSeconds)} · fallback`
  if (resolution.kind === 'blend') return 'display composite'
  return 'no frame here'
}

/** The accessible name of one story card. Every reading is named with its unit
 *  and an absent one is spoken as Unknown, so the card carries the same evidence
 *  by ear as by eye — a silently skipped field would read as a value not worth
 *  mentioning rather than one that was never returned. */
function storyCardLabel(item: StoryStep): string {
  const readings = [
    `temperature ${reading(item.temperatureC) === null ? 'unknown' : `${reading(item.temperatureC)} °C`}`,
    `dew point ${reading(item.dewPointC) === null ? 'unknown' : `${reading(item.dewPointC)} °C`}`,
    `precipitation probability ${item.precipPct === null ? 'unknown' : `${item.precipPct}%`}`,
    `wind ${item.windKmh === null ? 'unknown' : `${item.windKmh} km/h`}`,
  ]
  return `Scrub to ${item.time}. ${item.label}. ${readings.join(', ')}.`
}

/** One astronomy band beside the coverage rows: spans positioned by the same
 *  window fraction mapping, with the intervals named in a text alternative.
 *  Rendered only from a served response — never synthesized. */
function SkyBandRow({ label, intervals, windowStartMs, windowEndMs, description }: {
  label: string
  intervals: AstronomyInterval[]
  windowStartMs: number
  windowEndMs: number
  description: string
}) {
  const domain = windowEndMs - windowStartMs
  return (
    <div className="sky-band-row">
      <span className="sky-band-label">{label}</span>
      <div className="sky-band-track" role="img" aria-label={description}>
        {intervals.map((interval) => {
          const startMs = Math.max(new Date(interval.start).getTime(), windowStartMs)
          const endMs = Math.min(new Date(interval.end).getTime(), windowEndMs)
          if (!(endMs > startMs) || domain <= 0) return null
          const left = ((startMs - windowStartMs) / domain) * 100
          const width = ((endMs - startMs) / domain) * 100
          return <i key={`${interval.kind}-${interval.start}`} className={`sky-band sky-band-${interval.kind}`} style={{ left: `${left}%`, width: `${width}%` }} />
        })}
      </div>
    </div>
  )
}

function describeIntervals(name: string, intervals: AstronomyInterval[], empty: string): string {
  if (intervals.length === 0) return `${name}: ${empty}`
  return `${name}: ${intervals.map((interval) => `${interval.kind.replaceAll('_', ' ')} ${nlTime(interval.start)}-${nlTime(interval.end)} NT`).join(', ')}`
}

export interface StoryFlyoutProps {
  astronomy: AstronomyResponse | null
  astronomyNotice: string | null
  windowStartMs: number
  windowEndMs: number
  layers: LayerItem[]
  selections: LayerSelection[]
  onToggleLayer: (layerId: string) => void
  validTime: Date
  reference: Date
  timelineNotice: string | null
  story: StoryStep[]
  offsetMinutes: number
  onSelectOffsetHours: (offsetHours: number) => void
  onClose: () => void
}

export function StoryFlyout({
  astronomy, astronomyNotice, windowStartMs, windowEndMs, layers, selections, onToggleLayer,
  validTime, reference, timelineNotice, story, offsetMinutes, onSelectOffsetHours, onClose,
}: StoryFlyoutProps) {
  const containerRef = useRef<HTMLElement>(null)
  // Focus lands in the flyout when it opens, so Escape works immediately and
  // a screen reader hears where it is; the caller returns focus on close.
  useEffect(() => { containerRef.current?.focus() }, [])
  const groupedLayers = groupLayers(layers)
  return (
    <section
      ref={containerRef}
      id="story-flyout"
      className="story-flyout evidence-surface"
      aria-labelledby="story-title"
      aria-label={undefined}
      tabIndex={-1}
      onKeyDown={(event) => { if (event.key === 'Escape') onClose() }}
    >
      <div className="story-head-row">
        <div className="section-head">
          <span>02</span>
          <div><small>Scrub timeline (-3h to +24h)</small><h2 id="story-title">Weather story</h2></div>
        </div>
        <button type="button" className="story-flyout-close" onClick={onClose}>Close</button>
      </div>

      {astronomy !== null
        ? (
          <div className="sky-bands">
            <SkyBandRow
              label="Darkness"
              intervals={astronomy.twilight_bands.filter((band) => band.kind !== 'day')}
              windowStartMs={windowStartMs}
              windowEndMs={windowEndMs}
              description={describeIntervals('Darkness', astronomy.twilight_bands.filter((band) => band.kind !== 'day'), 'the sun stays up for this whole window')}
            />
            <SkyBandRow
              label="Moon up"
              intervals={astronomy.moon.above_horizon}
              windowStartMs={windowStartMs}
              windowEndMs={windowEndMs}
              description={describeIntervals('Moon above the horizon', astronomy.moon.above_horizon, 'the moon stays below the horizon for this whole window')}
            />
            <small className="sky-bands-note">Computed geometry (JPL DE442) — darkness and moon only; not cloud, transparency or light pollution.</small>
          </div>
        )
        : <p className="unwired-notice" role="status">Darkness and moon bands unavailable: {astronomyNotice ?? 'astronomy was not read'}. No band is drawn from a failure.</p>}

      <div className="coverage-ribbon" aria-label="Published frames per layer across the window">
        {layers.length === 0
          ? <p className="coverage-empty">No layer is published, so there are no frames to show.</p>
          : groupedLayers.map(({ group, label, rows }) => (
            // The same groups, order and headings as the layer drawer.
            // Rows keep the API's order inside each group.
            <section key={group} className="coverage-group" role="group" aria-labelledby={`coverage-group-${group}`}>
              <h4 id={`coverage-group-${group}`}>{label} · {rows.length} layer{rows.length === 1 ? '' : 's'}</h4>
              {group === 'satellite' && <p className="coverage-group-note">observed imagery: frames exist only for the past</p>}
              {rows.map((layer) => {
                const frames = (layer.times ?? [])
                  .map((time) => new Date(time).getTime())
                  .filter((stamp) => !Number.isNaN(stamp))
                const on = selections.some((entry) => entry.id === layer.id && entry.visible)
                // The ribbon names the quiet-or-fallback resolution; the
                // display-interpolation setting changes imagery, not this row.
                const resolution = resolveLayerFrame(layer, validTime, { interpolate: false, reference })
                return (
                  <div key={layer.id} className={`coverage-row ${on ? 'on' : 'off'}`}>
                    <button type="button" className="coverage-label" aria-pressed={on} onClick={() => onToggleLayer(layer.id)}>
                      {layer.title}
                    </button>
                    <div className="coverage-track" role="img" aria-label={coverageDescription(layer, frames.length, resolution)}>
                      {frames.map((stamp) => {
                        const fraction = (stamp - windowStartMs) / (windowEndMs - windowStartMs)
                        if (fraction < 0 || fraction > 1) return null
                        return <i key={stamp} className="coverage-frame" style={{ left: `${fraction * 100}%` }} />
                      })}
                    </div>
                    <span className="coverage-count">{ribbonLabel(frames.length, resolution)}</span>
                  </div>
                )
              })}
            </section>
          ))}
      </div>

      {/* The hours in the story come from /timeline. If that response did
          not declare a usable mode, it is said here rather than letting
          its hours read as coverage. */}
      {timelineNotice && <p className="unwired-notice" role="status">Published-hour coverage unavailable: {timelineNotice}. No story card is built from it.</p>}

      {story.length > 0 ? (
        <div className="story-track">
          {story.map((item, index) => (
            // A real <button>, not a div wearing role="button": Enter,
            // Space, focus order and the button role all come for free
            // and cannot drift apart. Its readings are laid out for the
            // eye, so the accessible name restates them in order with
            // their units — including every Unknown, which is the
            // reading that matters most and the easiest one to lose.
            <button
              key={item.time}
              type="button"
              style={{ '--step': index } as React.CSSProperties}
              className={`story-card ${item.offset * 60 === offsetMinutes ? 'active-hour' : ''}`}
              onClick={() => onSelectOffsetHours(item.offset)}
              aria-pressed={item.offset * 60 === offsetMinutes}
              aria-label={storyCardLabel(item)}
            >
              <time>{item.time}</time>
              <span className="temp">{reading(item.temperatureC) === null ? 'Unknown' : `${reading(item.temperatureC)}°`}</span>
              <strong>{item.label}</strong>
              <ModeChip mode={item.dataMode} />
              {/* Spans, not a <dl>: a button may only contain phrasing
                  content, and the button flattens list semantics into
                  its accessible name regardless. */}
              <span className="story-readings">
                <span><span className="story-key">Dew</span><span className="story-value">{reading(item.dewPointC) === null ? 'Unknown' : `${reading(item.dewPointC)}°`}</span></span>
                <span><span className="story-key">Rain</span><span className="story-value">{item.precipPct === null ? 'Unknown' : `${item.precipPct}%`}</span></span>
                <span><span className="story-key">Wind</span><span className="story-value">{item.windKmh === null ? 'Unknown' : item.windKmh}</span></span>
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="evidence-unavailable">24-hour narrative unavailable from this point response. No forecast story has been inferred.</p>
      )}
    </section>
  )
}
