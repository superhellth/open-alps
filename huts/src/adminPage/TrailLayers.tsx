import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'
import type L from 'leaflet'
import { leafletLayer, LineSymbolizer } from 'protomaps-leaflet'

const TRAILS_PMTILES_URL = '/data/trails.pmtiles'
const HUT_EDGES_PMTILES_URL = '/data/hut-edges.pmtiles'

/**
 * The raw OSM trail network (data/osm/trails.osm.pbf, ~26.5M nodes) is too large to ship as
 * GeoJSON, so it's pre-built (data/scripts/09-build-trail-tiles.py) into a single static
 * PMTiles vector-tile archive and rendered client-side via protomaps-leaflet - no tile server,
 * just an HTTP range-request-able file, same "no backend" shape as every other asset here.
 */
export function TrailTilesLayer({ visible }: { visible: boolean }) {
  const map = useMap()
  const layerRef = useRef<ReturnType<typeof leafletLayer> | null>(null)

  useEffect(() => {
    if (!layerRef.current) {
      layerRef.current = leafletLayer({
        url: TRAILS_PMTILES_URL,
        maxDataZoom: 14,
        paintRules: [
          {
            dataLayer: 'trails',
            symbolizer: new LineSymbolizer({ color: '#7b1fa2', width: 1, opacity: 0.5 }),
          },
        ],
      })
    }
    if (visible) layerRef.current.addTo(map)
    return () => {
      map.removeLayer(layerRef.current as unknown as L.Layer)
    }
  }, [map, visible])

  return null
}

/**
 * The derived hut-to-hut edges (data/osm/hut-edges.geojson, ~6,000 edges / ~7M vertices, ~184MB
 * as plain GeoJSON) render the same way the raw OSM network does - PMTiles + protomaps-leaflet,
 * not one React <Polyline> per edge - see data/scripts/11-build-hut-edge-tiles.py. Always on,
 * unlike TrailTilesLayer's toggle, since this is the admin view's primary layer.
 */
export function HutEdgeTilesLayer() {
  const map = useMap()
  const layerRef = useRef<ReturnType<typeof leafletLayer> | null>(null)

  useEffect(() => {
    layerRef.current = leafletLayer({
      url: HUT_EDGES_PMTILES_URL,
      maxDataZoom: 14,
      paintRules: [
        {
          dataLayer: 'hut_edges',
          symbolizer: new LineSymbolizer({ color: '#e65100', width: 2, opacity: 0.7 }),
        },
      ],
    })
    layerRef.current.addTo(map)
    return () => {
      map.removeLayer(layerRef.current as unknown as L.Layer)
    }
  }, [map])

  return null
}
