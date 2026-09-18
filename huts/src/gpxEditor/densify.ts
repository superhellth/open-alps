import { haversineM } from './snap.js'
import type { LonLat } from './types.js'

export function densify(from: LonLat, to: LonLat, maxStepM = 25): LonLat[] {
  const n = Math.ceil(haversineM(from, to) / maxStepM)
  const out: LonLat[] = []
  for (let i = 1; i < n; i++) {
    const t = i / n
    out.push({ lon: from.lon + (to.lon - from.lon) * t, lat: from.lat + (to.lat - from.lat) * t })
  }
  return out
}
