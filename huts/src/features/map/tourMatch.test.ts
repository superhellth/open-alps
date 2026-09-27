import { describe, it, expect } from 'vitest'
import { indexToursByEnd, indexToursByHut, indexToursByLeg, legKey, tierOf } from './tourMatch.js'
import type { RoutedTour, TierState } from './tourMatch.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { Route, RouteLeg } from './types.js'

const leg = (edgeId: number, layer: RouteLeg['layer'] = 'hut_edges', reversed = false): RouteLeg => ({ edgeId, reversed, layer })
const routed = (key: string, huts: number[], legs: RouteLeg[]): RoutedTour => ({
  key, tour: { huts, startId: 1 } as PlannerTour, route: { waypoints: [], legs } as Route,
})

describe('legKey', () => {
  it('includes the layer, since edge ids index layer-specific tables', () => {
    expect(legKey(leg(5, 'hut_edges'))).not.toBe(legKey(leg(5, 'start_edges')))
  })
  it('ignores direction', () => { expect(legKey(leg(5, 'hut_edges', true))).toBe(legKey(leg(5, 'hut_edges', false))) })
  it('is null for a leg without geometry', () => { expect(legKey(leg(-1))).toBeNull() })
})

describe('indexToursByLeg', () => {
  const a = routed('a', [10], [leg(5), leg(6)])
  const b = routed('b', [11], [leg(5, 'hut_edges', true), leg(7)])
  const c = routed('c', [12], [leg(5, 'start_edges'), leg(-1)])
  const d = routed('d', [13], [leg(-1)])
  const index = indexToursByLeg([a, b, c, d])
  it('lists every tour containing a leg, either direction', () => {
    expect(index.get(legKey(leg(5))!)).toEqual(['a', 'b'])
  })
  it('keeps the same edge id in another layer separate', () => {
    expect(index.get(legKey(leg(5, 'start_edges'))!)).toEqual(['c'])
  })
  it('never indexes legs without geometry', () => {
    expect([...index.keys()].some((k) => k.endsWith(':-1'))).toBe(false)
  })
  it('lists a tour once even when it uses a leg twice', () => {
    expect(indexToursByLeg([routed('x', [], [leg(5), leg(5)])]).get(legKey(leg(5))!)).toEqual(['x'])
  })
})

describe('indexToursByHut', () => {
  it('lists every tour that stops at a hut', () => {
    const index = indexToursByHut([routed('a', [10, 11], []), routed('b', [11], []), routed('c', [12], [])])
    expect(index.get(11)).toEqual(['a', 'b'])
    expect(index.get(12)).toEqual(['c'])
  })
})

describe('indexToursByEnd', () => {
  it('lists tours starting or ending at a start point, once per tour', () => {
    const r = (key: string, startId: number, exitStartId: number) => ({ ...routed(key, [], []), tour: { huts: [], startId, exitStartId } as unknown as PlannerTour })
    const index = indexToursByEnd([r('a', 1, 2), r('b', 2, 2), r('c', 1, 1)])
    expect(index.get(1)).toEqual(['a', 'c'])
    expect(index.get(2)).toEqual(['a', 'b'])
  })
})

describe('tierOf', () => {
  const state = (over: Partial<TierState> = {}): TierState => ({ hoveredKeys: new Set<string>(), focus: null, ...over })
  it('is rest by default', () => { expect(tierOf('k', state())).toBe('rest') })
  it('is focused inside the focus set', () => { expect(tierOf('k', state({ focus: new Set(['k']) }))).toBe('focused') })
  it('is rest outside the focus set', () => { expect(tierOf('k', state({ focus: new Set(['other']) }))).toBe('rest') })
  it('is hovered when its key is hovered, over focus', () => {
    expect(tierOf('k', state({ hoveredKeys: new Set(['k']), focus: new Set(['k']) }))).toBe('hovered')
  })
})
