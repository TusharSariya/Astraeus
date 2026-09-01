/** The timeline transport's model, kept pure so the rules are testable
 *  without a clock: the speed ladder, the direction, and where the selected
 *  instant lands after a slice of wall-clock time.
 *
 *  Playback moves nothing but the selected instant. Every layer still
 *  resolves that instant under its own published frames, so a played frame
 *  is exactly what a scrubbed one would have been. */

/** Weather-minutes advanced per wall-clock second. Each press doubles, so
 *  the top speed crosses the 28-hour window in a little under a minute. */
export const PLAYBACK_SPEEDS = [1, 2, 4, 8, 16, 32] as const

export type PlaybackSpeed = (typeof PLAYBACK_SPEEDS)[number]
export type PlaybackDirection = 1 | -1

/** The next rung up, or the same speed at the top of the ladder. */
export function fasterSpeed(speed: PlaybackSpeed): PlaybackSpeed {
  const index = PLAYBACK_SPEEDS.indexOf(speed)
  if (index < 0) return PLAYBACK_SPEEDS[0]
  return PLAYBACK_SPEEDS[Math.min(index + 1, PLAYBACK_SPEEDS.length - 1)]
}

/** The next rung down, or the same speed at the bottom of the ladder. */
export function slowerSpeed(speed: PlaybackSpeed): PlaybackSpeed {
  const index = PLAYBACK_SPEEDS.indexOf(speed)
  if (index < 0) return PLAYBACK_SPEEDS[0]
  return PLAYBACK_SPEEDS[Math.max(index - 1, 0)]
}

export interface AdvanceInput {
  /** The currently selected instant, epoch ms. */
  ms: number
  /** Wall-clock seconds since the previous animation frame. */
  elapsedSeconds: number
  speedMinutesPerSecond: number
  direction: PlaybackDirection
  windowStartMs: number
  windowEndMs: number
}

/** The selected instant after `elapsedSeconds` of playback, wrapping at the
 *  window edges (owner decision 2026-08-31: the timeline loops rather than
 *  stopping). The wrap is modular on the window length, so a long frame gap
 *  - a stalled tab, a slow paint - can never carry the clock past the far
 *  edge and out of the window. */
export function advanceClock({
  ms, elapsedSeconds, speedMinutesPerSecond, direction, windowStartMs, windowEndMs,
}: AdvanceInput): number {
  const span = windowEndMs - windowStartMs
  if (!(span > 0) || !Number.isFinite(elapsedSeconds) || elapsedSeconds <= 0) {
    return Math.max(windowStartMs, Math.min(windowEndMs, ms))
  }
  const stepped = ms + direction * elapsedSeconds * speedMinutesPerSecond * 60_000
  const offset = ((stepped - windowStartMs) % span + span) % span
  return windowStartMs + offset
}

/** The transport's readout: the speed with its direction, e.g. "16 min/s"
 *  or "16 min/s reversed". Callers render the arrow; this is the text an
 *  assistive reader hears. */
export function describeSpeed(speed: number, direction: PlaybackDirection): string {
  return `${speed} min/s${direction === -1 ? ' reversed' : ''}`
}
