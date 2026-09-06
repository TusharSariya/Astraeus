import { describe, expect, it } from 'vitest'
import { MARK_GAP_PX, placeScaleMarks, type MarkAnchor, type PlacedMark, type ScaleMark } from './scrubberAxis'

/** The dock's own marks, with the shorter form the boundaries fall back to. */
const MARKS: readonly ScaleMark[] = [
  { hours: -3, label: '-3h (Past)', short: '-3h' },
  { hours: -1, label: '-1h', short: '-1h' },
  { hours: 0, label: 'Now (0h)', short: 'Now (0h)' },
  { hours: 6, label: '+6h', short: '+6h' },
  { hours: 12, label: '+12h', short: '+12h' },
  { hours: 18, label: '+18h', short: '+18h' },
  { hours: 24, label: '+24h (Forecast)', short: '+24h' },
]

const BACK = 3 * 60
const FORWARD = 24 * 60

/** jsdom has no layout, so the widths come in from here rather than from a
 *  rendered node. 6 px per character is IBM Plex Mono at the rail's 10 px —
 *  the measurement the browser actually returns for this face. */
const measure = (text: string) => text.length * 6

function boxOf({ fraction, text, anchor }: PlacedMark, railPx: number): [number, number] {
  const x = fraction * railPx
  const w = measure(text)
  if (anchor === 'start') return [x, x + w]
  if (anchor === 'end') return [x - w, x]
  return [x - w / 2, x + w / 2]
}

function overlappingPairs(placed: PlacedMark[], railPx: number): string[] {
  const boxes = placed.map((mark) => ({ mark, box: boxOf(mark, railPx) }))
  const bad: string[] = []
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i], b = boxes[j]
      if (a.box[0] < b.box[1] && b.box[0] < a.box[1]) bad.push(`${a.mark.text} / ${b.mark.text}`)
    }
  }
  return bad
}

const place = (railPx: number) => placeScaleMarks({ marks: MARKS, backMinutes: BACK, forwardMinutes: FORWARD, railPx, measure })

describe('scrubber axis labels never overlap', () => {
  // The three widths of the failed 2026-09-02 browser pass: a 700 px and a
  // 900 px viewport, and the 1200 px viewport whose right conditions strip
  // leaves the rail about 860 px wide.
  it.each([700, 860, 900, 1200])('places no label over another on a %i px rail', (railPx) => {
    expect(overlappingPairs(place(railPx), railPx)).toEqual([])
  })

  it('holds from 600 px up, at every width in between', () => {
    const failures: Array<[number, string[]]> = []
    for (let railPx = 600; railPx <= 2000; railPx += 1) {
      const bad = overlappingPairs(place(railPx), railPx)
      if (bad.length > 0) failures.push([railPx, bad])
    }
    expect(failures).toEqual([])
  })

  it('keeps the past boundary, Now and the future boundary at every width', () => {
    for (let railPx = 600; railPx <= 2000; railPx += 10) {
      const hours = place(railPx).map((mark) => mark.hours)
      expect({ railPx, hours }).toEqual({ railPx, hours: expect.arrayContaining([-3, 0, 24]) })
    }
  })

  it('sheds a boundary suffix rather than the boundary itself when the rail is narrow', () => {
    const narrow = place(700)
    // The past end is where the crowding is — three marks inside the first
    // 4% of the axis — so `-3h (Past)` drops to `-3h` to clear `Now (0h)`.
    expect(narrow.find((mark) => mark.hours === -3)?.text).toBe('-3h')
    // The future end has 6 h of clear rail before it, so it keeps its words
    // even at 700 px: nothing is shortened that did not need to be.
    expect(narrow.find((mark) => mark.hours === 24)?.text).toBe('+24h (Forecast)')
    // `-1h` still cannot fit between them, so it is the one that goes: an
    // intermediate label, never a boundary and never `Now`.
    expect(narrow.map((mark) => mark.hours)).not.toContain(-1)
    expect(narrow.map((mark) => mark.hours)).toEqual([-3, 0, 6, 12, 18, 24])
  })

  it('restores the past boundary’s words as soon as the rail can hold them', () => {
    // `Now (0h)`'s left edge crosses clear of `-3h (Past)` at about 830 px,
    // so the words come back there and never flicker away again.
    const widths = [600, 700, 800, 860, 900, 1200]
    expect(widths.map((railPx) => place(railPx).find((mark) => mark.hours === -3)?.text))
      .toEqual(['-3h', '-3h', '-3h', '-3h (Past)', '-3h (Past)', '-3h (Past)'])
  })

  it('keeps the full labels once the rail is wide enough for them', () => {
    const wide = place(1600)
    expect(wide.find((mark) => mark.hours === -3)?.text).toBe('-3h (Past)')
    expect(wide.find((mark) => mark.hours === 24)?.text).toBe('+24h (Forecast)')
    expect(wide.map((mark) => mark.hours)).toEqual([-3, -1, 0, 6, 12, 18, 24])
  })

  it('returns the marks in axis order, not in the order they were placed', () => {
    for (const railPx of [700, 900, 1200, 1600]) {
      const hours = place(railPx).map((mark) => mark.hours)
      expect(hours).toEqual([...hours].sort((a, b) => a - b))
    }
  })

  it('anchors the boundaries inside the rail and centres the rest', () => {
    const placed = place(1600)
    const anchorOf = (hours: number): MarkAnchor | undefined => placed.find((mark) => mark.hours === hours)?.anchor
    expect(anchorOf(-3)).toBe('start')
    expect(anchorOf(24)).toBe('end')
    expect(anchorOf(0)).toBe('center')
    // Nothing is drawn off either end of the rail.
    for (const mark of placed) {
      const [left, right] = boxOf(mark, 1600)
      expect(left).toBeGreaterThanOrEqual(0)
      expect(right).toBeLessThanOrEqual(1600)
    }
  })

  it('leaves a real gap, not merely a touching edge', () => {
    for (const railPx of [700, 900, 1200]) {
      const placed = place(railPx)
      const boxes = placed.map((mark) => boxOf(mark, railPx)).sort((a, b) => a[0] - b[0])
      for (let i = 1; i < boxes.length; i += 1) {
        expect(boxes[i][0] - boxes[i - 1][1]).toBeGreaterThanOrEqual(MARK_GAP_PX)
      }
    }
  })

  it('renders every label in its long form before anything has been measured', () => {
    // First paint and any runtime without layout: the component must not
    // silently drop labels because it could not measure the rail.
    const unmeasured = placeScaleMarks({ marks: MARKS, backMinutes: BACK, forwardMinutes: FORWARD, railPx: 0, measure })
    expect(unmeasured.map((mark) => mark.text)).toEqual(MARKS.map((mark) => mark.label))
  })
})
