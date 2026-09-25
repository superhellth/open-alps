import type L from 'leaflet'
import type { EmphasisTier } from './types.js'

export type PaneRole = 'casing' | 'line' | 'symbol'

/** Route panes, bottom to top (overlayPane is 400, markerPane 600): per tier a casing, a line and a
 *  symbol pane, tiers ascending rest < focused < hovered. Fading is the pane's own CSS opacity rather
 *  than per-path alpha, so overlapping routes of one tier stay one flat colour instead of compounding,
 *  and no route's casing ever covers another route's line or symbols. */
const TIERS: Record<EmphasisTier, { base: number; opacity: number }> = {
  rest: { base: 410, opacity: 0.35 },
  focused: { base: 440, opacity: 0.7 },
  hovered: { base: 470, opacity: 1 },
}
const ROLE_OFFSET: Record<PaneRole, number> = { casing: 0, line: 10, symbol: 20 }

/** Invisible, always-on-top markers that receive hut hover/click; the visible symbols underneath never re-render on hover. */
export const HIT_PANE = 'route-hit'

export const paneName = (tier: EmphasisTier, role: PaneRole) => `route-${tier}-${role}`

function createPane(map: L.Map, name: string, z: number, opacity: number) {
  if (map.getPane(name)) return
  const pane = map.createPane(name)
  pane.style.zIndex = String(z)
  pane.style.opacity = String(opacity)
}

export function ensureRoutePanes(map: L.Map) {
  for (const tier of Object.keys(TIERS) as EmphasisTier[]) {
    for (const role of Object.keys(ROLE_OFFSET) as PaneRole[]) {
      createPane(map, paneName(tier, role), TIERS[tier].base + ROLE_OFFSET[role], TIERS[tier].opacity)
    }
  }
  createPane(map, HIT_PANE, 500, 1)
}
