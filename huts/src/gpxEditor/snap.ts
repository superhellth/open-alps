import type { Hub, LonLat } from './types.js'

const EARTH_R_M = 6_371_000
const M_PER_DEG_LAT = (EARTH_R_M * Math.PI) / 180
const CELL_DEG = 0.05
const MAX_RING = 400
const RAD = Math.PI / 180

export function haversineM(a: LonLat, b: LonLat): number {
  const p1 = a.lat * RAD
  const p2 = b.lat * RAD
  const dphi = (b.lat - a.lat) * RAD
  const dl = (b.lon - a.lon) * RAD
  const h = Math.sin(dphi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * EARTH_R_M * Math.asin(Math.sqrt(h))
}

export interface HubHit {
  hub: Hub
  distM: number
}

const cellKey = (ix: number, iy: number) => `${ix},${iy}`

export class HubIndex {
  private cells = new Map<string, Hub[]>()
  readonly size: number

  constructor(hubs: Hub[]) {
    this.size = hubs.length
    for (const h of hubs) {
      const k = cellKey(Math.floor(h.lon / CELL_DEG), Math.floor(h.lat / CELL_DEG))
      const bucket = this.cells.get(k)
      if (bucket) bucket.push(h)
      else this.cells.set(k, [h])
    }
  }

  within(p: LonLat, radiusM: number): HubHit[] {
    const cosLat = Math.max(0.01, Math.cos(p.lat * RAD))
    const dLat = radiusM / M_PER_DEG_LAT
    const dLon = radiusM / (M_PER_DEG_LAT * cosLat)
    const x0 = Math.floor((p.lon - dLon) / CELL_DEG)
    const x1 = Math.floor((p.lon + dLon) / CELL_DEG)
    const y0 = Math.floor((p.lat - dLat) / CELL_DEG)
    const y1 = Math.floor((p.lat + dLat) / CELL_DEG)
    const hits: HubHit[] = []
    for (let ix = x0; ix <= x1; ix++) {
      for (let iy = y0; iy <= y1; iy++) {
        for (const hub of this.cells.get(cellKey(ix, iy)) ?? []) {
          const distM = haversineM(p, hub)
          if (distM <= radiusM) hits.push({ hub, distM })
        }
      }
    }
    return hits
  }

  nearest(p: LonLat): HubHit | null {
    if (this.size === 0) return null
    const cx = Math.floor(p.lon / CELL_DEG)
    const cy = Math.floor(p.lat / CELL_DEG)
    // Narrower (lon) cell dimension, with a safety factor: unseen rings are >= r * cellM away.
    const cellM = CELL_DEG * M_PER_DEG_LAT * Math.max(0.01, Math.cos(p.lat * RAD)) * 0.9
    let best: HubHit | null = null
    const scan = (ix: number, iy: number) => {
      for (const hub of this.cells.get(cellKey(ix, iy)) ?? []) {
        const distM = haversineM(p, hub)
        if (!best || distM < best.distM) best = { hub, distM }
      }
    }
    for (let r = 0; r <= MAX_RING; r++) {
      for (let ix = cx - r; ix <= cx + r; ix++) {
        if (Math.abs(ix - cx) === r) {
          for (let iy = cy - r; iy <= cy + r; iy++) scan(ix, iy)
        } else {
          scan(ix, cy - r)
          scan(ix, cy + r)
        }
      }
      const found = best as HubHit | null
      if (found && found.distM <= r * cellM) break
    }
    return best
  }
}

export class SnapContext {
  readonly all: HubIndex
  readonly huts: HubIndex

  constructor(hubs: Hub[]) {
    this.all = new HubIndex(hubs)
    this.huts = new HubIndex(hubs.filter((h) => h.type === 'hut'))
  }
}

export interface SnapResult {
  chosen: Hub | null
  nearest: Hub | null
  nearestDistM: number
}

/** Mirrors pipeline lib/hubs.py nearest_hub_to_point on the pool match_tour_edges.py picks. */
export function snapPoint(ctx: SnapContext, point: LonLat, maxSnapM: number, requireHut: boolean): SnapResult {
  const pool = requireHut ? ctx.huts : ctx.all
  const nearest = pool.nearest(point)
  if (!nearest) return { chosen: null, nearest: null, nearestDistM: Infinity }
  const inRange = pool.within(point, maxSnapM)
  if (inRange.length === 0) return { chosen: null, nearest: nearest.hub, nearestDistM: nearest.distM }
  const huts = inRange.filter((h) => h.hub.type === 'hut')
  const candidates = huts.length > 0 ? huts : inRange
  const chosen = candidates.reduce((a, b) => (b.distM < a.distM ? b : a))
  return { chosen: chosen.hub, nearest: nearest.hub, nearestDistM: nearest.distM }
}
