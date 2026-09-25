import { useEffect } from 'react'
import L from 'leaflet'
import { useMap } from 'react-leaflet'

/** One shared tooltip for leg and hut hover, opened at the pointer's entry point while `tip` is set. */
export default function HoverTooltip({ tip }: { tip: { at: L.LatLng; html: string } | null }) {
  const map = useMap()
  useEffect(() => {
    if (!tip) return
    const tooltip = L.tooltip({ direction: 'top', offset: [0, -8], opacity: 0.95 }).setLatLng(tip.at).setContent(tip.html)
    map.openTooltip(tooltip)
    return () => { map.closeTooltip(tooltip) }
  }, [map, tip])
  return null
}
