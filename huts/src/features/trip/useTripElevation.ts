import { useEffect, useState } from 'react'
import { loadLegElevation } from '@/tourSearch/loadLegElevation.js'
import { legLayer } from '@/tourSearch/loadLegGeometry.js'
import type { TripLegs } from '@/trip/tripLegs.js'

export interface ElevationPoint {
  distanceKm: number
  elevationM: number
  legIndex: number
}

export interface TripElevation {
  points: ElevationPoint[]
  /** Cumulative distanceKm at each night boundary: start, each hut, exit (legs.length + 1 entries). */
  nightBoundariesKm: number[]
  loading: boolean
}

const NO_LEGS: TripLegs['legs'] = []
const EMPTY: TripElevation = { points: [], nightBoundariesKm: [], loading: false }

/** Loads and concatenates every leg's elevation series on the main thread (byte-range fetches via
 *  loadLegElevation); a leg with no edge (null, or edgeId < 0) contributes a boundary but no
 *  points. Distance within a leg is spread evenly across its sample count — the payload does not
 *  carry per-sample distance, only the leg total. */
export function useTripElevation(tripLegs: TripLegs | null): TripElevation {
  const legs = tripLegs?.legs ?? NO_LEGS
  const [state, setState] = useState<TripElevation>({ points: [], nightBoundariesKm: [], loading: legs.length > 0 })
  const key = legs.map((l) => (l ? `${l.edgeId}:${l.reversed}` : 'null')).join(',')

  useEffect(() => {
    if (!tripLegs || legs.length === 0) { setState(EMPTY); return }
    let cancelled = false
    setState((s) => ({ ...s, loading: true }))

    async function run() {
      const points: ElevationPoint[] = []
      const nightBoundariesKm: number[] = [0]
      let cumulativeKm = 0
      for (let i = 0; i < legs.length; i++) {
        const leg = legs[i]
        if (!leg || leg.edgeId < 0) {
          nightBoundariesKm.push(cumulativeKm)
          continue
        }
        const layer = legLayer(i, legs.length)
        const values = await loadLegElevation(layer, leg.edgeId, leg.reversed)
        const legKm = leg.distanceM / 1000
        values.forEach((elevationM, j) => {
          const fraction = values.length > 1 ? j / (values.length - 1) : 0
          points.push({ distanceKm: cumulativeKm + fraction * legKm, elevationM, legIndex: i })
        })
        cumulativeKm += legKm
        nightBoundariesKm.push(cumulativeKm)
      }
      if (!cancelled) setState({ points, nightBoundariesKm, loading: false })
    }
    run()
    return () => { cancelled = true }
    // tripLegs.legs is captured through `key`.
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  return state
}
