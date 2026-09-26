import { describe, it, expect } from 'vitest'
import { createTourClusterer, markerRadius } from './clusterTours.js'

const WORLD: [number, number, number, number] = [-180, -85, 180, 85]
const points = [
  { key: 'a', lat: 47.0, lng: 11.0 },
  { key: 'b', lat: 47.001, lng: 11.001 },
  { key: 'c', lat: 47.001, lng: 11.001 },
  { key: 'd', lat: 48.5, lng: 13.0 },
]

describe('createTourClusterer', () => {
  const clusterer = createTourClusterer(points)

  it('zoomed out, clusters count their tours', () => {
    const items = clusterer.clustersFor(WORLD, 2)
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({ kind: 'cluster', count: 4 })
  })

  it('zoomed in, resolves to single tours', () => {
    const items = clusterer.clustersFor(WORLD, 15)
    expect(items.map((m) => (m.kind === 'tour' ? m.key : '')).sort()).toEqual(['a', 'b', 'c', 'd'])
  })

  it('lists the tour keys inside a cluster', () => {
    const [cluster] = clusterer.clustersFor(WORLD, 2)
    if (cluster.kind !== 'cluster') throw new Error('expected a cluster')
    expect(clusterer.keysOf(cluster.clusterId).sort()).toEqual(['a', 'b', 'c', 'd'])
  })

  it('handles no tours', () => {
    expect(createTourClusterer([]).clustersFor(WORLD, 5)).toEqual([])
  })
})

describe('markerRadius', () => {
  it('grows with the count, sub-linearly, inside fixed bounds', () => {
    expect(markerRadius(1)).toBeLessThan(markerRadius(10))
    expect(markerRadius(100)).toBeLessThan(10 * markerRadius(10))
    expect(markerRadius(1)).toBeGreaterThanOrEqual(12)
    expect(markerRadius(1_000_000)).toBeLessThanOrEqual(34)
  })
})
