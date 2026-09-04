import { SOURCE_TYPE_PARKING, SOURCE_TYPE_PARTNER, SOURCE_TYPE_STATION } from '../tourSearch/types.js'
import type { SearchResult, TourResult } from '../tourSearch/types.js'
import type { FreeByOffset } from '../availability/types.js'
import type { GeometryLayer } from '../tourSearch/loadLegGeometry.js'
import type { OfficialTourView } from '../tourSearch/officialTours.js'
import type { Route, RouteWaypoint, StartPoint } from './types.js'

export const PAGE_SIZE = 25

export const SOURCE_TYPE_LABEL: Record<number, string> = {
  [SOURCE_TYPE_STATION]: 'Bahnhof',
  [SOURCE_TYPE_PARKING]: 'Parkplatz',
  [SOURCE_TYPE_PARTNER]: 'Partnerbetrieb',
}

export type SortKey = 'duration' | 'ascent' | 'distance' | 'legCount'

export const SORT_COMPARATORS: Record<SortKey, (a: TourResult, b: TourResult) => number> = {
  duration: (a, b) => a.totalDurationH - b.totalDurationH,
  ascent: (a, b) => a.totalAscentM - b.totalAscentM,
  distance: (a, b) => a.totalDistanceM - b.totalDistanceM,
  legCount: (a, b) => a.huts.length - b.huts.length,
}

export const SORT_LABEL: Record<SortKey, string> = {
  duration: 'Gesamtdauer',
  ascent: 'Anstieg',
  distance: 'Distanz',
  legCount: 'Etappenzahl',
}

// Translates raw kill-counter keys into actionable German guidance (spec D1: killCounters must
// not be rendered raw). Shown only in the empty-results state.
const KILL_COUNTER_GUIDANCE: Record<string, (n: number) => string> = {
  maxLegTime: (n) => `${n} Etappen waren zu lang — maximale Gehzeit erhöhen`,
  minLegTime: (n) => `${n} Etappen waren zu kurz — minimale Gehzeit senken`,
  legAscentCap: (n) => `${n} Etappen hatten zu viel Anstieg — Anstiegslimit erhöhen`,
  maxEleM: (n) => `${n} Etappen lagen über der Maximalhöhe — Maximalhöhe erhöhen`,
  viaFerrata: (n) => `${n} Etappen enthielten Klettersteige — "Klettersteige erlauben" aktivieren`,
  revisit: () => '', // internal search bookkeeping, not user-actionable
  hutFiltered: (n) => `${n} mögliche Etappenziele wurden durch den Hüttenfilter ausgeschlossen — Hüttenarten wieder aktivieren`,
}

export function killCounterGuidance(killCounters: SearchResult['killCounters']): string[] {
  return Object.entries(killCounters)
    .filter(([key, n]) => n > 0 && KILL_COUNTER_GUIDANCE[key]?.(n))
    .map(([key, n]) => KILL_COUNTER_GUIDANCE[key](n))
}

// Zips chain.legs (engine-side, name-agnostic) against the point sequence [start, ...huts, exit]
// to produce one "from → to" label per leg, without the engine ever knowing about hut/start names.
export function legWaypointLabels(
  chain: TourResult,
  startLabel: (startId: number) => string,
  hutNameById: Map<number, string>,
): string[] {
  const pointLabels = [
    startLabel(chain.startId),
    ...chain.huts.map((h) => hutNameById.get(h) ?? String(h)),
    startLabel(chain.exitStartId),
  ]
  const labels: string[] = []
  for (let i = 0; i < pointLabels.length - 1; i++) labels.push(`${pointLabels[i]} → ${pointLabels[i + 1]}`)
  return labels
}

// legCountMax above this is flagged as potentially slow in the UI (spec D2: "guard the
// expensive end of the range" - no Worker, no cancel, so an unexpected blowup freezes the tab).
export const LEG_COUNT_SLOW_WARNING_THRESHOLD = 8

// Shown instead of the generic empty-results message when mode === 'village': only 56 of 110
// Partnerbetriebe are connected to the trail network, so zero results there far more often
// reflects sparse coverage than an over-tight filter.
export const VILLAGE_EMPTY_STATE_HINT =
  'Nur wenige Bergsteigerdörfer/Partnerbetriebe sind an das Wegenetz angebunden — probiere einen anderen Modus, falls hier keine Touren erscheinen.'

// OSM feature ids in parking.geojson/stations.geojson are prefixed ("n123") - approaches.startId
// is the bare numeric OSM node id, so this strips the prefix to join the two.
export function idFromOsmFeatureId(featureId: string | number): number | null {
  const n = Number(String(featureId).replace(/^\D+/, ''))
  return Number.isFinite(n) ? n : null
}

export function toNumberOrDefault(value: string, fallback: number): number {
  if (value === '') return fallback
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

export type AvailabilityBadge = 'free' | 'unavailable' | 'direct' | 'unknown' | null

/** Mirrors search.ts's hutAvailable() classification (spec §3), but returns which of the four UI
 *  states applies instead of a pass/fail boolean — used for badges-only mode, where every hut in
 *  an already-found chain is labeled independently of whether the search itself was constrained. */
export function hutAvailabilityBadge(
  hutIndex: number,
  offsetDays: number,
  ohrsIdByHutIndex: Map<number, string | null> | null,
  freeByOffset: FreeByOffset | null,
): AvailabilityBadge {
  if (!ohrsIdByHutIndex || !freeByOffset) return null
  const ohrsId = ohrsIdByHutIndex.get(hutIndex)
  if (ohrsId == null) return 'direct'
  const free = freeByOffset.get(offsetDays)
  if (free === 'unknown' || free === undefined) return 'unknown'
  return free.has(ohrsId) ? 'free' : 'unavailable'
}

export const AVAILABILITY_BADGE_LABEL: Record<Exclude<AvailabilityBadge, null>, string> = {
  free: 'frei',
  unavailable: 'ausgebucht/geschlossen',
  direct: 'Direktbuchung',
  unknown: 'unbekannt',
}

export const AVAILABILITY_BADGE_COLOR: Record<Exclude<AvailabilityBadge, null>, string> = {
  free: '#2e7d32',
  unavailable: '#c62828',
  direct: '#616161',
  unknown: '#9e9e9e',
}

export function legLayer(legIndex: number, legCount: number): GeometryLayer {
  return legIndex === 0 || legIndex === legCount - 1 ? 'start_edges' : 'hut_edges'
}

export function chainToRoute(
  chain: TourResult,
  hutCoordsById: Map<number, { lat: number; lng: number }>,
  startById: Map<number, StartPoint>,
): Route {
  const startPoint = startById.get(chain.startId)
  const endPoint = startById.get(chain.exitStartId)
  const hutPoints = chain.huts.map((h) => hutCoordsById.get(h)).filter((p): p is { lat: number; lng: number } => !!p)
  const waypoints: RouteWaypoint[] = [
    ...(startPoint ? [{ lat: startPoint.lat, lng: startPoint.lng }] : []),
    ...hutPoints,
    ...(endPoint ? [{ lat: endPoint.lat, lng: endPoint.lng }] : []),
  ]
  return {
    waypoints,
    legs: chain.legs.map((leg, i) => ({
      edgeId: leg.edgeId, reversed: leg.reversed, layer: legLayer(i, chain.legs.length),
    })),
  }
}

function officialTourEndpointCoords(
  endpoint: { type: string; id: number },
  hutCoordsById: Map<number, { lat: number; lng: number }>,
  startById: Map<number, StartPoint>,
): RouteWaypoint | null {
  const p = endpoint.type === 'hut' ? hutCoordsById.get(endpoint.id) : startById.get(endpoint.id)
  return p ? { lat: p.lat, lng: p.lng } : null
}

export function officialTourToRoute(
  tour: OfficialTourView,
  hutCoordsById: Map<number, { lat: number; lng: number }>,
  startById: Map<number, StartPoint>,
): Route | null {
  if (tour.legs.length === 0) return null
  const first = officialTourEndpointCoords(tour.legs[0].from, hutCoordsById, startById)
  if (!first) return null
  const waypoints: RouteWaypoint[] = [first]
  for (const leg of tour.legs) {
    const to = officialTourEndpointCoords(leg.to, hutCoordsById, startById)
    if (!to) return null
    waypoints.push(to)
  }
  return {
    waypoints,
    legs: tour.legs.map((leg) => ({ edgeId: leg.edgeId, reversed: leg.reversed, layer: 'tour_edges' as const })),
  }
}
