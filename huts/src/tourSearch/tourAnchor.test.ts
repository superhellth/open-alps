import { describe, it, expect } from 'vitest'
import { anchorCandidates, tourAnchor } from './tourAnchor.js'
import type { AnchorRoute } from './tourAnchor.js'
import type { LegAnchorLookup } from './legAnchors.js'

const WORLD: [number, number, number, number] = [-180, -90, 180, 90]
const none: LegAnchorLookup = () => null
const leg = (edgeId: number, distanceM: number, reversed = false) => ({ layer: 'hut_edges' as const, edgeId, reversed, distanceM })
const pt = (lat: number, lng: number) => ({ lat, lng })

// Two legs west->east, 1000 m each, anchors known for edge 0 (a, b, c), chord for edge 1.
const route: AnchorRoute = { waypoints: [pt(47, 11), pt(47, 11.4), pt(47, 11.8)], legs: [leg(0, 1000), leg(1, 1000)] }
const stored: LegAnchorLookup = (_l, id) => (id === 0 ? [pt(47.01, 11.1), pt(47.02, 11.2), pt(47.03, 11.3)] : null)

describe('tourAnchor', () => {
  it('picks the candidate closest to half the tour distance', () => {
    // half = 1000 m: leg 0 spans 0..1000 (anchors at 250/500/750), leg 1 spans 1000..2000 (chord 1250/1500/1750)
    const a = tourAnchor(route, stored, WORLD)!
    expect(a.lat).toBeCloseTo(47.03, 6)   // 750 m is the nearest to 1000 m
    expect(a.lng).toBeCloseTo(11.3, 6)
  })

  it('swaps the 25 and 75 % anchors of a reversed leg', () => {
    const rev: AnchorRoute = { waypoints: [pt(47, 11.4), pt(47, 11)], legs: [leg(0, 1000, true)] }
    const a = tourAnchor(rev, stored, WORLD)!
    // candidates in walking order: 11.3 @250, 11.2 @500, 11.1 @750; half = 500 -> the 50 % anchor
    expect(a.lng).toBeCloseTo(11.2, 6)
    const rev2: AnchorRoute = { waypoints: [pt(47, 11.4), pt(47, 11), pt(47, 10.6)], legs: [leg(0, 1000, true), leg(5, 1)] }
    // half = 500.5: nearest is the 50 % anchor again, but now with 25/75 swapped it must still be 11.2
    expect(tourAnchor(rev2, stored, WORLD)!.lng).toBeCloseTo(11.2, 6)
  })

  it('takes the chord point when a leg has no shipped anchors or edgeId < 0', () => {
    const r: AnchorRoute = { waypoints: [pt(47, 11), pt(47, 11.4)], legs: [leg(-1, 1000)] }
    const a = tourAnchor(r, none, WORLD)!
    expect(a.lat).toBeCloseTo(47, 6)
    expect(a.lng).toBeCloseTo(11.2, 6)
  })

  it('heads west when the route runs westward at the anchor, else east', () => {
    const west: AnchorRoute = { waypoints: [pt(47, 11.4), pt(47, 11)], legs: [leg(-1, 1000)] }
    expect(tourAnchor(west, none, WORLD)!.heading).toBe('west')
    expect(tourAnchor(route, none, WORLD)!.heading).toBe('east')
  })

  it('derives the heading from the neighbouring candidates, not the whole leg', () => {
    // the leg doubles back: at the 50 % anchor the previous anchor (11.3) lies east of the next (11.1), so the travel there is west
    const bulge: LegAnchorLookup = () => [pt(47, 11.3), pt(47, 10.9), pt(47, 11.1)]
    const r: AnchorRoute = { waypoints: [pt(47, 11), pt(47, 11.4)], legs: [leg(0, 1000)] }
    expect(tourAnchor(r, bulge, WORLD)!.heading).toBe('west')
  })

  it('falls back to the in-view candidate closest to half the distance', () => {
    // bbox covers only lng 11.0..11.15: only the 25 % anchor (11.1) is inside
    const a = tourAnchor(route, stored, [11.0, 46, 11.15, 48])!
    expect(a.lng).toBeCloseTo(11.1, 6)
  })

  it('returns null when no candidate lies in the viewport', () => {
    expect(tourAnchor(route, stored, [12.5, 46, 13, 48])).toBeNull()
  })

  it('still yields an anchor for a tour of zero total distance', () => {
    const r: AnchorRoute = { waypoints: [pt(47, 11), pt(47, 11.4)], legs: [leg(-1, 0)] }
    expect(tourAnchor(r, none, WORLD)).not.toBeNull()
  })

  it('returns null for a route without legs', () => {
    expect(tourAnchor({ waypoints: [pt(47, 11)], legs: [] }, none, WORLD)).toBeNull()
  })

  it('handles a lookup that ships only the 50 % anchor', () => {
    const one: LegAnchorLookup = () => [pt(47.05, 11.2)]
    const r: AnchorRoute = { waypoints: [pt(47, 11), pt(47, 11.4)], legs: [leg(0, 1000)] }
    expect(tourAnchor(r, one, WORLD)!.lat).toBeCloseTo(47.05, 6)
  })
})

describe('anchorCandidates', () => {
  // half = 1000 m. Leg 0 anchors at 250/500/750 (lng 11.1/11.2/11.3), leg 1 chord points at 1250/1500/1750 (11.5/11.6/11.7).
  it('orders every candidate by distance from half the tour, ties in walking order', () => {
    const lngs = anchorCandidates(route, stored, WORLD).map((c) => c.lng)
    const expected = [11.3, 11.5, 11.2, 11.6, 11.1, 11.7]
    expect(lngs).toHaveLength(expected.length)
    lngs.forEach((lng, i) => expect(lng).toBeCloseTo(expected[i], 6))
  })

  it('keeps only candidates inside the bbox', () => {
    const lngs = anchorCandidates(route, stored, [11.0, 46, 11.35, 48]).map((c) => c.lng)
    expect(lngs).toHaveLength(3)
    ;[11.3, 11.2, 11.1].forEach((lng, i) => expect(lngs[i]).toBeCloseTo(lng, 6))
  })

  it('keeps the heading of each candidate', () => {
    const west: AnchorRoute = { waypoints: [pt(47, 11.4), pt(47, 11)], legs: [leg(-1, 1000)] }
    expect(anchorCandidates(west, none, WORLD).every((c) => c.heading === 'west')).toBe(true)
  })

  it('is empty when nothing is in view or the route has no legs', () => {
    expect(anchorCandidates(route, stored, [12.5, 46, 13, 48])).toEqual([])
    expect(anchorCandidates({ waypoints: [pt(47, 11)], legs: [] }, none, WORLD)).toEqual([])
  })

  it('starts with the tourAnchor choice', () => {
    expect(anchorCandidates(route, stored, WORLD)[0]).toEqual(tourAnchor(route, stored, WORLD))
  })
})
