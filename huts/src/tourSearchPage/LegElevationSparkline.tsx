import { useEffect, useState } from 'react'
import { loadLegElevation } from '../tourSearch/loadLegElevation.js'
import type { GeometryLayer } from '../tourSearch/loadLegGeometry.js'
import ElevationSparkline from '../ElevationSparkline.js'

/** Fetches and renders one leg's height profile - only mounted while that leg's row/segment is
 *  hovered, so the elevation series is never fetched for legs the user hasn't looked at. */
export default function LegElevationSparkline({
  layer, edgeId, reversed,
}: {
  layer: GeometryLayer
  edgeId: number
  reversed: boolean
}) {
  const [values, setValues] = useState<number[] | null>(null)

  useEffect(() => {
    setValues(null)
    let cancelled = false
    loadLegElevation(layer, edgeId, reversed).then((v) => {
      if (!cancelled) setValues(v)
    })
    return () => {
      cancelled = true
    }
  }, [layer, edgeId, reversed])

  return <ElevationSparkline values={values} />
}
