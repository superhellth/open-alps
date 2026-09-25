import { useEffect, useMemo, useState } from 'react'
import type { SearchClient } from '../search/searchClient.js'
import { overlapLegsOf } from '@/trip/tripOverlaps.js'
import type { TripLegs } from '@/trip/tripLegs.js'
import type { Trip } from '../trip/trip.js'

/** Overlap between an edited trip's legs is a warning, not a block; the tables live in the worker. */
export function useTripOverlaps(client: SearchClient | null, trip: Trip, tripLegs: TripLegs): string[] {
  const legs = useMemo(() => overlapLegsOf(tripLegs), [tripLegs])
  const loopClosure = trip.start.startId === trip.exit.startId
  const [pairs, setPairs] = useState<[number, number][]>([])
  const key = legs ? `${loopClosure}|${legs.map((l) => `${l.kind}${l.edgeId}${l.reversed ? 'r' : ''}`).join(',')}` : 'none'

  useEffect(() => {
    if (!client || !legs || legs.length === 0) { setPairs([]); return }
    let cancelled = false
    client.overlaps(legs, loopClosure).then(
      (p) => { if (!cancelled) setPairs(p) },
      () => { if (!cancelled) setPairs([]) },
    )
    return () => { cancelled = true }
  }, [client, key]) // eslint-disable-line react-hooks/exhaustive-deps

  return useMemo(() => pairs.map(([earlier, later]) => `Etappe ${later + 1} überschneidet sich mit Etappe ${earlier + 1}`), [pairs])
}
