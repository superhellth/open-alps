export interface StartGroup<T> {
  startId: number
  tours: T[]
}

/** The start point with the most matching tours; ties go to the lowest startId. Used to auto-zoom
 *  the map to a sensible cluster when nothing is selected yet. */
export function bestStartId<T>(groups: StartGroup<T>[]): number | null {
  let best: StartGroup<T> | null = null
  for (const g of groups) {
    if (!best || g.tours.length > best.tours.length || (g.tours.length === best.tours.length && g.startId < best.startId)) {
      best = g
    }
  }
  return best?.startId ?? null
}

export function groupByStart<T extends { startId: number }>(tours: T[]): StartGroup<T>[] {
  const byStart = new Map<number, StartGroup<T>>()
  for (const tour of tours) {
    let group = byStart.get(tour.startId)
    if (!group) {
      group = { startId: tour.startId, tours: [] }
      byStart.set(tour.startId, group)
    }
    group.tours.push(tour)
  }
  return [...byStart.values()]
}
