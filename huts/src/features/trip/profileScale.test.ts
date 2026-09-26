import { describe, it, expect } from 'vitest'
import {
  PROFILE_HEIGHT, PROFILE_MARGINS, elevationAxis, formatKm, fractionInLeg, legAtKm, makeScales, nearestPoint, placeStopLabels, truncateLabel,
} from './profileScale.js'
import type { ElevationPoint } from './useTripElevation.js'

const points: ElevationPoint[] = [
  { distanceKm: 0, elevationM: 1000, legIndex: 0 }, { distanceKm: 0.5, elevationM: 1200, legIndex: 0 },
  { distanceKm: 1, elevationM: 1400, legIndex: 1 }, { distanceKm: 1.5, elevationM: 1300, legIndex: 1 },
]

describe('elevationAxis', () => {
  it('uses 250 m steps when the span is under 1000 m and pads to whole steps', () => {
    expect(elevationAxis(1000, 1400)).toEqual({ lo: 1000, hi: 1500 })
  })
  it('uses 500 m steps for larger spans', () => {
    expect(elevationAxis(800, 2100)).toEqual({ lo: 500, hi: 2500 })
  })
  it('never collapses a flat profile to zero height', () => {
    const axis = elevationAxis(1000, 1000)
    expect(axis.hi).toBeGreaterThan(axis.lo)
  })
})

describe('makeScales', () => {
  const s = makeScales(points, [0, 1, 1.5], 600)
  it('maps km 0 and the trip end to the plot edges', () => {
    expect(s.x(0)).toBe(PROFILE_MARGINS.left)
    expect(s.x(1.5)).toBe(600 - PROFILE_MARGINS.right)
  })
  it('maps the axis limits to the plot bottom and top', () => {
    expect(s.y(s.axis.lo)).toBe(PROFILE_HEIGHT - PROFILE_MARGINS.bottom)
    expect(s.y(s.axis.hi)).toBe(PROFILE_MARGINS.top)
  })
  it('kmAt inverts x and clamps to the plot', () => {
    expect(s.kmAt(s.x(0.75))).toBeCloseTo(0.75)
    expect(s.kmAt(-50)).toBe(0)
    expect(s.kmAt(10_000)).toBeCloseTo(1.5)
  })
  it('reports the lowest and highest sample', () => {
    expect([s.minM, s.maxM]).toEqual([1000, 1400])
  })
  it('produces finite coordinates for a flat profile', () => {
    const flat = makeScales([{ distanceKm: 0, elevationM: 900, legIndex: 0 }, { distanceKm: 1, elevationM: 900, legIndex: 0 }], [0, 1], 600)
    expect(Number.isFinite(flat.y(900))).toBe(true)
  })
})

describe('legAtKm / fractionInLeg', () => {
  const bounds = [0, 1, 1.5]
  it('finds the leg containing a km value, the last leg at the very end', () => {
    expect(legAtKm(bounds, 0)).toBe(0)
    expect(legAtKm(bounds, 0.99)).toBe(0)
    expect(legAtKm(bounds, 1)).toBe(1)
    expect(legAtKm(bounds, 1.5)).toBe(1)
  })
  it('skips a zero-length leg (a leg without data)', () => {
    expect(legAtKm([0, 0, 1], 0)).toBe(1)
  })
  it('returns the fraction along a leg, clamped, 0 for a zero-length leg', () => {
    expect(fractionInLeg(bounds, 1, 1.25)).toBeCloseTo(0.5)
    expect(fractionInLeg(bounds, 0, 5)).toBe(1)
    expect(fractionInLeg([0, 0, 1], 0, 0)).toBe(0)
  })
})

describe('nearestPoint', () => {
  it('returns the point closest in km', () => {
    expect(nearestPoint(points, 0.4)).toBe(points[1])
    expect(nearestPoint(points, 1.4)).toBe(points[3])
    expect(nearestPoint(points, -3)).toBe(points[0])
  })
})

describe('truncateLabel / formatKm', () => {
  it('keeps a label that fits and ellipsizes one that does not', () => {
    expect(truncateLabel('Hütte', 200)).toBe('Hütte')
    expect(truncateLabel('Kaiserhaus am See', 52)).toMatch(/…$/)
    expect(truncateLabel('Kaiserhaus am See', 52).length).toBeLessThanOrEqual(8)
  })
  it('drops the label when there is no room', () => {
    expect(truncateLabel('Hütte', 4)).toBe('')
    expect(truncateLabel('Hütte', -10)).toBe('')
  })
  it('formats km with one German decimal', () => {
    expect(formatKm(18.24)).toBe('18,2')
    expect(formatKm(0)).toBe('0,0')
  })
})

describe('placeStopLabels', () => {
  it('centres hut names exactly on their lines', () => {
    const labels = placeStopLabels([40, 200, 400, 560], ['Start', 'Hütte A', 'Hütte B', 'Ende'], 600)
    expect(labels.slice(1, 3)).toEqual([{ x: 200, text: 'Hütte A' }, { x: 400, text: 'Hütte B' }])
  })
  it('falls back to the stage number, then to nothing, when a hut name does not fit', () => {
    const labels = placeStopLabels([0, 40, 60, 100], ['S', 'Hütte A', 'Hütte B', 'E'], 100)
    expect(labels[1].text).toBe('1')
    expect(placeStopLabels([0, 50, 50, 100], ['S', 'A', 'B', 'E'], 100)[1].text).toBe('')
  })
  it('shifts the start and exit names inside the width and ellipsizes them to their space', () => {
    const [start, , end] = placeStopLabels([10, 300, 590], ['Bahnhof', 'Hütte', 'Parkplatz'], 600, 6)
    expect(start).toEqual({ x: 21, text: 'Bahnhof' })
    expect(end.x + (end.text.length * 6) / 2).toBeLessThanOrEqual(600)
    expect(placeStopLabels([0, 100], ['Bahnhof Mayrhofen', 'Ende'], 200, 6)[0].text).toMatch(/…$/)
  })
})
