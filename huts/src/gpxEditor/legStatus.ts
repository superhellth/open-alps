import { LONG_SEGMENT_M, segmentLengthsM } from './segments.js'
import { snapPoint, type SnapContext, type SnapResult } from './snap.js'
import type { LonLat } from './types.js'

export interface LegShape {
  first: LonLat
  last: LonLat
  maxSegmentM: number
}

export function legShape(points: LonLat[]): LegShape | null {
  if (points.length < 2) return null
  return {
    first: points[0]!,
    last: points[points.length - 1]!,
    maxSegmentM: Math.max(...segmentLengthsM(points)),
  }
}

export interface LegStatus {
  start: SnapResult
  end: SnapResult
  startOk: boolean
  endOk: boolean
  longSegment: boolean
}

/** position = index in the tour's numerically sorted leg list (not the leg number). */
export function endpointRequiresHut(position: number, nLegs: number): { start: boolean; end: boolean } {
  return { start: position !== 0, end: position !== nLegs - 1 }
}

export function legStatus(
  ctx: SnapContext, shape: LegShape, position: number, nLegs: number, maxSnapM: number,
): LegStatus {
  const req = endpointRequiresHut(position, nLegs)
  const start = snapPoint(ctx, shape.first, maxSnapM, req.start)
  const end = snapPoint(ctx, shape.last, maxSnapM, req.end)
  return {
    start, end,
    startOk: start.chosen !== null,
    endOk: end.chosen !== null,
    longSegment: shape.maxSegmentM > LONG_SEGMENT_M,
  }
}

/** True when some leg's end hub differs from the next leg's start hub (informational badge). */
export function tourDiscontinuous(statuses: (LegStatus | null)[]): boolean {
  for (let i = 0; i + 1 < statuses.length; i++) {
    const a = statuses[i]?.end.chosen
    const b = statuses[i + 1]?.start.chosen
    if (a && b && (a.id !== b.id || a.type !== b.type)) return true
  }
  return false
}
