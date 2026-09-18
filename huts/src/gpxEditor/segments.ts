import type { Pt } from './decimate.js'
import { haversineM } from './snap.js'
import type { LonLat } from './types.js'

export const LONG_SEGMENT_M = 150

export function segmentLengthsM(points: LonLat[]): number[] {
  const out: number[] = []
  for (let i = 1; i < points.length; i++) out.push(haversineM(points[i - 1]!, points[i]!))
  return out
}

function distToSegment(p: Pt, a: Pt, b: Pt): number {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const len2 = dx * dx + dy * dy
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2))
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy))
}

export function nearestSegment(px: Pt[], click: Pt): { index: number; distPx: number } {
  let best = { index: 0, distPx: Infinity }
  for (let i = 0; i + 1 < px.length; i++) {
    const d = distToSegment(click, px[i]!, px[i + 1]!)
    if (d < best.distPx) best = { index: i, distPx: d }
  }
  return best
}
