import { useEffect, useState } from 'react'
import { loadLegGeometry } from '../../tourSearch/loadLegGeometry.js'
import type { Route } from '../types.js'

/** Resolves each leg's real trail geometry. An entry stays null while its fetch is in flight, if it
 *  rejects, or when the leg has no geometry (edgeId < 0); the caller draws a straight segment then. */
export function useLegGeometries(route: Route | null): ([number, number][] | null)[] {
  const [geometries, setGeometries] = useState<([number, number][] | null)[]>([])

  useEffect(() => {
    if (!route || route.waypoints.length !== route.legs.length + 1) {
      setGeometries([])
      return
    }
    const legs = route.legs
    setGeometries(new Array(legs.length).fill(null))
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
        () => {},
      )
    })
    return () => { cancelled = true }
  }, [route])

  return geometries
}
