import { useMemo, useState } from 'react'
import L from 'leaflet'
import { Marker, useMap, useMapEvents } from 'react-leaflet'
import type { StartGroup } from '../../tourSearch/groupByStart.js'
import type { PlannerTour } from '../tours.js'
import type { StartPoint } from '../types.js'
import { createStartClusterer, markerRadius } from './clusterStarts.js'
import './map.css'

interface View {
  bbox: [number, number, number, number]
  zoom: number
}

// The bounds are padded by half a tile-width so markers just outside the viewport (and a
// zero-size map, as in jsdom) still resolve.
function currentView(map: L.Map): View {
  const b = map.getBounds()
  const zoom = Math.round(map.getZoom())
  const pad = (0.5 * 360) / 2 ** zoom
  return { bbox: [b.getWest() - pad, b.getSouth() - pad, b.getEast() + pad, b.getNorth() + pad], zoom }
}

const iconCache = new Map<string, L.DivIcon>()
function countIcon(count: number, dimmed: boolean): L.DivIcon {
  const key = `${count}|${dimmed}`
  let icon = iconCache.get(key)
  if (!icon) {
    const size = Math.round(markerRadius(count) * 2)
    icon = L.divIcon({
      className: `start-count-marker${dimmed ? ' dimmed' : ''}`,
      html: `<span>${count}</span>`,
      iconSize: [size, size],
    })
    iconCache.set(key, icon)
  }
  return icon
}

/** One marker per start point with matching tours, clustered by zoom; a cluster shows the sum of
 *  its members' match counts. Panning and zooming only re-cluster, they never re-search. */
export default function DiscoverLayer({ groups, startById, dimmed, onSelectStarts }: {
  groups: StartGroup<PlannerTour>[]
  startById: Map<number, StartPoint>
  dimmed: boolean
  onSelectStarts: (startIds: number[]) => void
}) {
  const map = useMap()
  const [view, setView] = useState(() => currentView(map))
  useMapEvents({ moveend: () => setView(currentView(map)), zoomend: () => setView(currentView(map)) })

  const clusterer = useMemo(() => createStartClusterer(groups.flatMap((g) => {
    const s = startById.get(g.startId)
    return s ? [{ startId: g.startId, count: g.tours.length, lat: s.lat, lng: s.lng }] : []
  })), [groups, startById])

  return (
    <>
      {clusterer.clustersFor(view.bbox, view.zoom).map((m) => (
        <Marker
          key={m.kind === 'start' ? `s${m.startId}` : `c${m.clusterId}`}
          position={[m.lat, m.lng]}
          icon={countIcon(m.count, dimmed)}
          eventHandlers={{
            click: () => {
              if (m.kind === 'start') { onSelectStarts([m.startId]); return }
              map.flyTo([m.lat, m.lng], Math.min(clusterer.expansionZoom(m.clusterId), map.getMaxZoom()))
              onSelectStarts(clusterer.startIdsOf(m.clusterId))
            },
          }}
        />
      ))}
    </>
  )
}
