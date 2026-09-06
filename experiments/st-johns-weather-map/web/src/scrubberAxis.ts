/** Placing the scrubber's scale labels so that none is drawn over another.
 *
 *  The marks sit at fixed offsets on a 27-hour axis, so the first three
 *  (`-3h (Past)`, `-1h`, `Now (0h)`) are only 1 h and 3 h apart: about 3.7% of
 *  the rail. On a rail narrower than roughly 1150 px that is less than the
 *  width of the labels themselves, and they overlapped — three strings drawn
 *  on top of each other at the left end, in every theme and every state.
 *
 *  This is pure geometry over MEASURED widths, kept out of the component so it
 *  can be checked at real rail widths without a layout engine. Nothing here
 *  touches the frame markers or the quick jumps: they have their own rails. */

export type MarkAnchor = 'start' | 'center' | 'end'

export interface ScaleMark {
  hours: number
  /** The full label, used whenever it fits. */
  label: string
  /** The same instant said in fewer characters, tried before the mark is
   *  dropped. Only the two boundary marks have a shorter form to fall back
   *  to; for the rest it is the label itself. */
  short: string
}

export interface PlacedMark {
  hours: number
  /** The text actually rendered: `label`, or `short` when the long form did
   *  not fit. */
  text: string
  fraction: number
  anchor: MarkAnchor
}

/** Minimum clear space between two labels. Below this they are legible but
 *  read as one string, which is its own kind of misreading on a time axis. */
export const MARK_GAP_PX = 8

function boxOf(x: number, width: number, anchor: MarkAnchor): [number, number] {
  if (anchor === 'start') return [x, x + width]
  if (anchor === 'end') return [x - width, x]
  return [x - width / 2, x + width / 2]
}

function overlaps(a: [number, number], b: [number, number], gap: number): boolean {
  return a[0] < b[1] + gap && b[0] < a[1] + gap
}

/** Which labels to draw on a rail of `railPx`, and in which form.
 *
 *  Marks are placed in priority order — `Now`, then the future boundary, then
 *  the past boundary, then the rest in axis order — and a mark is placed only
 *  if its box clears every box already placed. A boundary mark tries its long
 *  form first and its short form second, so it survives a narrow rail by
 *  shedding its "(Past)" / "(Forecast)" suffix rather than by disappearing:
 *  from 600 px up the short forms always fit, so the three marks that carry
 *  the axis's meaning are always on screen.
 *
 *  `railPx <= 0` means nothing has been measured yet (first paint, or a
 *  runtime with no layout). Every mark is then returned in its long form,
 *  which is exactly what the component rendered before this existed. */
export function placeScaleMarks({ marks, backMinutes, forwardMinutes, railPx, measure, gapPx = MARK_GAP_PX }: {
  marks: readonly ScaleMark[]
  backMinutes: number
  forwardMinutes: number
  railPx: number
  measure: (text: string) => number
  gapPx?: number
}): PlacedMark[] {
  const span = backMinutes + forwardMinutes
  const candidates = marks
    .map((mark) => ({ mark, fraction: (mark.hours * 60 + backMinutes) / span }))
    .filter(({ fraction }) => fraction >= 0 && fraction <= 1)
    .map(({ mark, fraction }) => ({
      mark,
      fraction,
      anchor: (fraction === 0 ? 'start' : fraction === 1 ? 'end' : 'center') as MarkAnchor,
    }))

  if (railPx <= 0) {
    return candidates.map(({ mark, fraction, anchor }) => ({ hours: mark.hours, text: mark.label, fraction, anchor }))
  }

  const byHours = new Map(candidates.map((entry) => [entry.mark.hours, entry]))
  const first = candidates[0]
  const last = candidates[candidates.length - 1]
  const now = byHours.get(0)
  // The three that carry the axis's meaning go first, so a narrow rail sheds
  // an intermediate label rather than the boundary the reader orients by.
  const priority = [now, last, first, ...candidates].filter((entry, index, all): entry is typeof candidates[number] =>
    !!entry && all.indexOf(entry) === index)

  const placed: Array<{ order: number; box: [number, number]; mark: PlacedMark }> = []
  priority.forEach((entry) => {
    const x = entry.fraction * railPx
    for (const text of entry.mark.label === entry.mark.short ? [entry.mark.label] : [entry.mark.label, entry.mark.short]) {
      const box = boxOf(x, measure(text), entry.anchor)
      if (placed.some(({ box: taken }) => overlaps(box, taken, gapPx))) continue
      placed.push({
        order: candidates.indexOf(entry),
        box,
        mark: { hours: entry.mark.hours, text, fraction: entry.fraction, anchor: entry.anchor },
      })
      return
    }
  })
  // Back into axis order: priority decided what survives, not what is drawn
  // where, and the DOM order is what a screen reader follows.
  return placed.sort((a, b) => a.order - b.order).map(({ mark }) => mark)
}

/** The width of one label in the rail's own font, via a canvas rather than a
 *  hidden DOM node, so measuring never forces a second layout pass mid-scrub.
 *  Returns 0 when the runtime has no 2-D canvas, which `placeScaleMarks`
 *  treats as "unmeasured" and answers with the full label set. */
export function textMeasurer(font: string, transform: (text: string) => string = (text) => text): (text: string) => number {
  const context = typeof document === 'undefined' ? null : document.createElement('canvas').getContext('2d')
  if (!context) return () => 0
  context.font = font
  return (text) => context.measureText(transform(text)).width
}
