import { describe, it, expect } from 'vitest'
import { anchorMarkerKind, createAnchorClusterer, createStartClusterer, markerRadius } from './clusterStarts.js'
import type { AnchorMarker } from './clusterStarts.js'

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

describe('markerRadius', () => {
  it('grows with the count, sub-linearly, inside fixed bounds', () => {
    expect(markerRadius(1)).toBeLessThan(markerRadius(10))
    expect(markerRadius(100)).toBeLessThan(10 * markerRadius(10))
    expect(markerRadius(1)).toBeGreaterThanOrEqual(12)
    expect(markerRadius(1_000_000)).toBeLessThanOrEqual(34)
  })
})

describe('createAnchorClusterer', () => {
  const points = [
    { tourKey: 'best', lat: 47.0, lng: 11.0 },
    { tourKey: 'near', lat: 47.0001, lng: 11.0001 },
    { tourKey: 'far', lat: 48.5, lng: 13.0 },
  ]
  const clusterer = createAnchorClusterer(points)

  it('groups nearby anchors into one marker whose foot is the best-ranked tour\'s own anchor', () => {
    const markers = clusterer.markersFor(WORLD, 13)
    const stack = markers.find((m) => m.tourKeys.length === 2)!
    expect(stack.tourKeys).toEqual(['best', 'near'])
    expect(stack.lat).toBe(47.0)
    expect(stack.lng).toBe(11.0)
    expect(stack.id).toBe('best')
  })

  it('keeps distant anchors as single markers', () => {
    const markers = clusterer.markersFor(WORLD, 13)
    expect(markers.find((m) => m.tourKeys[0] === 'far')!.tourKeys).toEqual(['far'])
  })

  it('ranks by input order even when the cluster tree returns members differently', () => {
    const reversed = createAnchorClusterer([...points.slice(0, 2)].reverse())
    expect(reversed.markersFor(WORLD, 13).find((m) => m.tourKeys.length === 2)!.tourKeys).toEqual(['near', 'best'])
  })

  it('separates every anchor past the clusterer\'s max zoom', () => {
    expect(clusterer.markersFor(WORLD, 20).map((m) => m.tourKeys.length)).toEqual([1, 1, 1])
  })

  it('handles no points', () => { expect(createAnchorClusterer([]).markersFor(WORLD, 13)).toEqual([]) })
})

describe('anchorMarkerKind', () => {
  const m = (n: number): AnchorMarker => ({ id: 'a', lat: 0, lng: 0, tourKeys: Array.from({ length: n }, (_, i) => `k${i}`) })
  it('is single for one tour and stack for several', () => {
    expect(anchorMarkerKind(m(1))).toBe('single')
    expect(anchorMarkerKind(m(3))).toBe('stack')
  })
})
