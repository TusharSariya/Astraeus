/** The always-visible timeline dock under the map: scrubber, quick jumps,
 *  the valid-instant badge, the display-interpolation toggle and the story
 *  panel toggle. Presentational — every behaviour is the caller's handler,
 *  so the snap rules live in one place (App) for both this and the expert
 *  slider. */

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
  interpolate: boolean
  onToggleInterpolate: () => void
  storyOpen: boolean
  onToggleStory: () => void
  storyToggleRef: React.RefObject<HTMLButtonElement | null>
}

const QUICK_JUMPS = [-3, -1, 0, 3, 6, 12, 18, 24]

const SCALE_MARKS: Array<{ hours: number; label: string }> = [
  { hours: -3, label: '-3h (Past)' },
  { hours: -1, label: '-1h' },
  { hours: 0, label: 'Now (0h)' },
  { hours: 6, label: '+6h' },
  { hours: 12, label: '+12h' },
  { hours: 18, label: '+18h' },
  { hours: 24, label: '+24h (Forecast)' },
]

export function TimelineDock({
  offsetMinutes, scrubOffset, validClock, backMinutes, forwardMinutes, snapping, ariaValueText,
  onScrubMinutes, onScrubKeyDown, onQuickJump, interpolate, onToggleInterpolate, storyOpen, onToggleStory, storyToggleRef,
}: TimelineDockProps) {
  return (
    <section className="timeline-dock" aria-label="Scrub timeline">
      <div className="timeline-dock-head">
        <div className="story-scrubber-badge">
          <span>Valid:</span>
          <strong>{offsetMinutes === 0 ? `Now (0h) · ${validClock} NT` : `${scrubOffset} (${offsetMinutes < 0 ? 'Past' : 'Forecast'}) · ${validClock} NT`}</strong>
        </div>
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
          <div className="scrubber-labels">
            {SCALE_MARKS.map(({ hours, label }) => {
              const fraction = (hours * 60 + backMinutes) / (backMinutes + forwardMinutes)
              if (fraction < 0 || fraction > 1) return null
              const edge = fraction === 0 ? 'start' : fraction === 1 ? 'end' : ''
              return (
                <span
                  key={hours}
                  className={`scrubber-mark ${edge} ${hours === 0 ? 'scrubber-now' : ''}`}
                  style={{ left: `${fraction * 100}%` }}
                >
                  {label}
                </span>
              )
            })}
          </div>
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
        </div>
        <div className="scrubber-quick-jumps">
          {QUICK_JUMPS.map((offset) => (
            <button key={offset} type="button" className={offsetMinutes === offset * 60 ? 'active' : ''} onClick={() => onQuickJump(offset)}>
              {offset === 0 ? 'Now' : offset > 0 ? `+${offset}h` : `${offset}h`}
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}
