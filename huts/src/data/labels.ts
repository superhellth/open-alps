import { SOURCE_TYPE_PARKING, SOURCE_TYPE_PARTNER, SOURCE_TYPE_STATION } from '@/tourSearch/types.js'
import type { StartPoint } from './types.js'

export const SOURCE_TYPE_LABEL: Record<number, string> = {
  [SOURCE_TYPE_STATION]: 'Bahnhof',
  [SOURCE_TYPE_PARKING]: 'Parkplatz',
  [SOURCE_TYPE_PARTNER]: 'Partnerbetrieb',
}

// OSM feature ids in parking.geojson/stations.geojson are prefixed ("n123"); approaches.startId is
// the bare numeric OSM node id, so this strips the prefix to join the two.
export function idFromOsmFeatureId(featureId: string | number): number | null {
  const digits = String(featureId).replace(/^\D+/, '')
  if (digits === '') return null
  const n = Number(digits)
  return Number.isFinite(n) ? n : null
}

export function makeStartLabel(startById: Map<number, StartPoint>): (startId: number) => string {
  return (startId) => {
    const start = startById.get(startId)
    if (!start) return `Startpunkt ${startId}`
    const kind = SOURCE_TYPE_LABEL[start.sourceType] ?? 'Startpunkt'
    if (!start.name) return kind
    return start.sourceType === SOURCE_TYPE_STATION ? start.name : `${start.name} (${kind})`
  }
}
