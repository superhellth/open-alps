import L from 'leaflet'
import { Marker, useMap } from 'react-leaflet'
import { hutSymbolSvg, startSymbolSvg } from './hutSymbol.js'
import { HIT_PANE, ensureRoutePanes, paneName } from './routePanes.js'
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

const HUT_SIZE = 18
const END_SIZE = 16
const iconCache = new Map<string, L.DivIcon>()

function symbolIcon(stop: WaypointStop, selected: boolean): L.DivIcon {
  const key = stop.type === 'hut' ? `h|${stop.operator}|${stop.serviced}|${selected}` : `e|${stop.sourceType}`
  let icon = iconCache.get(key)
  if (!icon) {
    const size = stop.type === 'hut' ? HUT_SIZE : END_SIZE
    icon = L.divIcon({
      className: stop.type === 'hut' ? 'hut-marker' : 'start-symbol',
      html: stop.type === 'hut'
        ? hutSymbolSvg({ operator: stop.operator, serviced: stop.serviced, selected, size })
        : startSymbolSvg(stop.sourceType, size),
      iconSize: [size, size], iconAnchor: [size / 2, size / 2],
    })
    iconCache.set(key, icon)
  }
  return icon
}

const HIT_ICON = L.divIcon({ className: 'waypoint-hit', html: '', iconSize: [24, 24], iconAnchor: [12, 12] })

/** Hut and end-point symbols of every visible route. The visible symbols are display-only; hut hover and
 *  click go through invisible hit markers above them, so hovering never replaces the element under the pointer. */
export default function WaypointLayer({ symbols, onHoverHut, onClickHut }: {
  symbols: WaypointSymbol[]
  onHoverHut: (hutId: number | null, at: L.LatLng) => void
  onClickHut: (hutId: number) => void
}) {
  const map = useMap()
  ensureRoutePanes(map)
  return (
    <>
      {symbols.map((s) => (
        <Marker
          key={`${s.id}-${s.tier}`} position={[s.lat, s.lng]} pane={paneName(s.tier, 'symbol')}
          icon={symbolIcon(s.stop, s.tier === 'hovered' && s.stop.type === 'hut')} interactive={false} keyboard={false}
        />
      ))}
      {symbols.flatMap((s) => {
        if (s.stop.type !== 'hut') return []
        const { hutId } = s.stop
        return [
          <Marker
            key={`hit-${s.id}`} position={[s.lat, s.lng]} pane={HIT_PANE} icon={HIT_ICON} keyboard={false}
            eventHandlers={{
              mouseover: (e) => onHoverHut(hutId, e.latlng),
              mouseout: (e) => onHoverHut(null, e.latlng),
              click: () => onClickHut(hutId),
            }}
          />,
        ]
      })}
    </>
  )
}
