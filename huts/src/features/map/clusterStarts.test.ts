import { describe, it, expect } from 'vitest'
import { createStartClusterer, markerKind } from './clusterStarts.js'
import type { MapMarker } from './clusterStarts.js'

const WORLD: [number, number, number, number] = [-180, -85, 180, 85]
const markers = [
  { startId: 1, count: 3, lat: 47.0, lng: 11.0 },
  { startId: 2, count: 4, lat: 47.001, lng: 11.001 },
  { startId: 3, count: 2, lat: 48.5, lng: 13.0 },
]

describe('createStartClusterer', () => {
  const clusterer = createStartClusterer(markers)

  it('zoomed out, clusters carry the sum of their members\' match counts', () => {
    const items = clusterer.clustersFor(WORLD, 2)
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({ kind: 'cluster', count: 9 })
  })

  it('zoomed in, resolves to single start points with their own counts', () => {
    const items = clusterer.clustersFor(WORLD, 15)
    expect(items.map((m) => m.kind)).toEqual(['start', 'start', 'start'])
    expect(items.map((m) => (m.kind === 'start' ? m.startId : -1)).sort()).toEqual([1, 2, 3])
    expect(items.find((m) => m.kind === 'start' && m.startId === 2)?.count).toBe(4)
  })

  it('lists the start ids inside a cluster and a zoom that splits it', () => {
    const [cluster] = clusterer.clustersFor(WORLD, 2)
    if (cluster.kind !== 'cluster') throw new Error('expected a cluster')
    expect(clusterer.startIdsOf(cluster.clusterId).sort()).toEqual([1, 2, 3])
    expect(clusterer.expansionZoom(cluster.clusterId)).toBeGreaterThan(2)
  })

  it('handles no markers', () => {
    expect(createStartClusterer([]).clustersFor(WORLD, 5)).toEqual([])
  })
})

describe('markerKind', () => {
  const start = (count: number): MapMarker => ({ kind: 'start', startId: 1, count, lat: 0, lng: 0 })
  it('is single for one start point with one tour', () => { expect(markerKind(start(1))).toBe('single') })
  it('is stack for one start point with several tours', () => { expect(markerKind(start(3))).toBe('stack') })
  it('is cluster for several start points, whatever the count', () => {
    expect(markerKind({ kind: 'cluster', clusterId: 1, count: 1, lat: 0, lng: 0 })).toBe('cluster')
  })
})
