export interface StartGroup<T> {
  startId: number
  tours: T[]
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
