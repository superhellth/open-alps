import { useCallback, useRef, useState } from 'react'
import L from 'leaflet'
import { ROUTE_REVEAL_ZOOM } from './DiscoverLayer.js'
import type { View } from '@/lib/viewport.js'

export interface ViewTarget { lat: number; lng: number; zoom: number }
export type Bounds = [[number, number], [number, number]]

/** Map viewport state: the live view, the pre-trip view to restore, and fit-to-bounds commands. */
export function useMapView() {
  const [mapView, setMapView] = useState<View | null>(null)
  const [restoreView, setRestoreView] = useState<ViewTarget | null>(null)
  const [fitBounds, setFitBounds] = useState<Bounds | null>(null)
  const preTripView = useRef<ViewTarget | null>(null)
  const viewRef = useRef<View | null>(null)
  viewRef.current = mapView

  // Below ROUTE_REVEAL_ZOOM the map shows only count markers, so a hovered tour highlights its bubble instead of drawing a route.
  const routesVisible = mapView !== null && mapView.zoom >= ROUTE_REVEAL_ZOOM

  const rememberViewBeforeTrip = useCallback(() => {
    const v = viewRef.current
    if (v) preTripView.current = { lat: (v.bbox[1] + v.bbox[3]) / 2, lng: (v.bbox[0] + v.bbox[2]) / 2, zoom: v.zoom }
  }, [])
  const restoreViewAfterTrip = useCallback(() => {
    if (preTripView.current) setRestoreView({ ...preTripView.current })
  }, [])
  const fitToPoints = useCallback((points: { lat: number; lng: number }[]) => {
    const bounds = L.latLngBounds([])
    for (const p of points) bounds.extend([p.lat, p.lng])
    if (bounds.isValid()) setFitBounds([[bounds.getSouth(), bounds.getWest()], [bounds.getNorth(), bounds.getEast()]])
  }, [])

  return { mapView, setMapView, routesVisible, restoreView, fitBounds, rememberViewBeforeTrip, restoreViewAfterTrip, fitToPoints }
}
