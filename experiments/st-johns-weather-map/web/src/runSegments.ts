/** Run segments derived from `layer.frames[]` (task 4.3): consecutive frames
 *  sharing one `run_time`, so the frame-marker rail can label each segment
 *  and mark the point where the run changes — a short cycle leaving the
 *  previous run serving leads the new one lacks (design.md, "Why a short
 *  cycle keeps the previous run"). Pure geometry, no DOM, so it can be
 *  checked directly. */

import type { LayerFrame } from './types'

export interface RunSegment {
  /** Null when this segment's run time is unknown. Never adopted from a
   *  neighbouring segment — an unknown run stays unknown. */
  runTime: string | null
  unknown: boolean
  /** Set only when `unknown`; the reason shown in place of a run time. */
  reason: string | null
  frames: LayerFrame[]
  /** Index into the original `frames[]` array. */
  startIndex: number
  endIndex: number
  /** Title/aria text for the segment: "run <time>" or "run unknown: <reason>". */
  label: string
}

const UNKNOWN_RUN_REASON = 'run time not declared for this frame'

function labelFor(runTime: string | null, unknown: boolean, reason: string | null): string {
  return unknown ? `run unknown: ${reason ?? UNKNOWN_RUN_REASON}` : `run ${runTime}`
}

/** The frames grouped into segments, in frame order. Two adjacent frames
 *  merge into one segment only when both declare the same non-null run
 *  time; two adjacent frames that are each individually unknown are two
 *  separate one-frame segments, never merged into a shared "unknown"
 *  segment — that would imply they came from one run when neither says so. */
export function runSegments(frames: LayerFrame[]): RunSegment[] {
  const segments: RunSegment[] = []
  frames.forEach((frame, index) => {
    const runTime = frame.run_time ?? null
    const unknown = runTime === null
    const previous = segments[segments.length - 1]
    if (previous && !unknown && !previous.unknown && previous.runTime === runTime) {
      previous.frames.push(frame)
      previous.endIndex = index
      return
    }
    const reason = unknown ? UNKNOWN_RUN_REASON : null
    segments.push({
      runTime,
      unknown,
      reason,
      frames: [frame],
      startIndex: index,
      endIndex: index,
      label: labelFor(runTime, unknown, reason),
    })
  })
  return segments
}

/** The frame indices where the run changes between adjacent frames — where
 *  the rail draws its small change-point marker. The first frame is never a
 *  change point: nothing precedes it to change from. */
export function runChangePoints(segments: RunSegment[]): number[] {
  return segments.slice(1).map((segment) => segment.startIndex)
}
