import type { EmphasisTier, Route, WaypointStop } from './types.js'

export interface WaypointSymbol {
  /** `h<hutIndex>` or `e<startId>`. */
  id: string
  lat: number
  lng: number
  stop: WaypointStop
  tier: EmphasisTier
}

const TIER_RANK: Record<EmphasisTier, number> = { rest: 0, focused: 1, hovered: 2 }

/** One symbol per unique hut or end point across the given routes, at the highest tier of any route through it. */
export function collectSymbols(items: { route: Route; tier: EmphasisTier }[]): WaypointSymbol[] {
  const byId = new Map<string, WaypointSymbol>()
  for (const { route, tier } of items) {
    for (const w of route.waypoints) {
      if (!w.stop) continue
      const id = w.stop.type === 'hut' ? `h${w.stop.hutId}` : `e${w.stop.startId}`
      const seen = byId.get(id)
      if (!seen) byId.set(id, { id, lat: w.lat, lng: w.lng, stop: w.stop, tier })
      else if (TIER_RANK[tier] > TIER_RANK[seen.tier]) seen.tier = tier
    }
  }
  return [...byId.values()]
}
