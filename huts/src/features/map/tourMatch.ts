import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { EmphasisTier, Route, RouteLeg } from './types.js'

export interface RoutedTour {
  key: string
  tour: PlannerTour
  route: Route
}

/** A leg's identity across tours. Edge ids index a table per layer, so the layer is part of the key;
 *  a leg without geometry (edgeId < 0) is never shared. */
export function legKey(leg: RouteLeg): string | null {
  return leg.edgeId < 0 ? null : `${leg.layer}:${leg.edgeId}`
}

function pushOnce<K>(index: Map<K, string[]>, id: K, key: string) {
  const list = index.get(id)
  if (!list) index.set(id, [key])
  else if (list[list.length - 1] !== key) list.push(key)
}

/** Leg key → keys of every tour containing that leg (either direction). */
export function indexToursByLeg(routed: RoutedTour[]): Map<string, string[]> {
  const index = new Map<string, string[]>()
  for (const { key, route } of routed) {
    for (const leg of route.legs) {
      const id = legKey(leg)
      if (id !== null) pushOnce(index, id, key)
    }
  }
  return index
}

/** Hut index → keys of every tour stopping at that hut. */
export function indexToursByHut(routed: RoutedTour[]): Map<number, string[]> {
  const index = new Map<number, string[]>()
  for (const { key, tour } of routed) for (const hut of tour.huts) pushOnce(index, hut, key)
  return index
}

export interface TierState {
  hoveredKeys: ReadonlySet<string>
  hoveredStarts: ReadonlySet<number> | null
  focus: ReadonlySet<string> | null
}

export function tierOf(tour: { key: string; startId: number }, s: TierState): EmphasisTier {
  if (s.hoveredKeys.has(tour.key)) return 'hovered'
  if (s.focus?.has(tour.key) || s.hoveredStarts?.has(tour.startId)) return 'focused'
  return 'rest'
}
