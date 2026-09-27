import { useEffect, useState } from 'react'
import { loadLegGeometry } from '@/tourSearch/loadLegGeometry.js'
import type { Route } from './types.js'

/** Resolves each leg's real trail geometry. An entry is undefined while its fetch is in flight
 *  (the caller draws nothing yet) and null if it rejected or the leg has no geometry (edgeId < 0);
 *  the caller draws a straight segment then. */
export function useLegGeometries(route: Route | null): ([number, number][] | null | undefined)[] {
  const [geometries, setGeometries] = useState<([number, number][] | null | undefined)[]>([])

  useEffect(() => {
    if (!route || route.waypoints.length !== route.legs.length + 1) {
      setGeometries([])
      return
    }
    const legs = route.legs
    setGeometries(legs.map((leg) => (leg.edgeId < 0 ? null : undefined)))
    let cancelled = false
    legs.forEach((leg, i) => {
      if (leg.edgeId < 0) return
      loadLegGeometry(leg.layer, leg.edgeId, leg.reversed).then(
        (points) => {
          if (cancelled) return
          setGeometries((prev) => {
            const next = [...prev]
            next[i] = points
            return next
          })
        },
        () => {
          if (cancelled) return
          setGeometries((prev) => {
            const next = [...prev]
            next[i] = null
            return next
          })
        },
      )
    })
    return () => { cancelled = true }
  }, [route])

  return geometries
}
