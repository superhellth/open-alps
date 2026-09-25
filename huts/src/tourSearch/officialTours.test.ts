import { describe, it, expect } from 'vitest'
import { buildOfficialTourViews } from './officialTours.js'
import type { RawTour } from './loadOfficialTours.js'

const scalars = (d: number, up: number, down: number, s: number, max: number) =>
  ({ distanceM: d, ascentM: up, descentM: down, durationS: s, maxEleM: max })

const completeTour: RawTour = {
  tourId: 1, name: 'Welser Höhenweg', numDays: 2,
  legs: [
    { legIndex: 0, edgeId: 0, ...scalars(6000, 800, 100, 7200, 1400), from: { type: 'parking', id: 1 }, to: { type: 'hut', id: 302 } },
    { legIndex: 1, edgeId: 1, ...scalars(10000, 1000, 800, 10800, 2000), from: { type: 'hut', id: 302 }, to: { type: 'hut', id: 376 } },
  ],
}

describe('buildOfficialTourViews', () => {
  it('builds a view from tours.json scalars, using durationS for durationH', () => {
    const [view] = buildOfficialTourViews([completeTour])
    expect(view.legs[0]).toMatchObject({
      legIndex: 0, edgeId: 0, reversed: false, distanceM: 6000, ascentM: 800, descentM: 100,
      durationH: 2, maxEleM: 1400, from: { type: 'parking', id: 1 }, to: { type: 'hut', id: 302 },
    })
    expect(view.legs[0]).not.toHaveProperty('sacRank')
    expect(view.legs[0]).not.toHaveProperty('viaFerrata')
    expect(view.totalDistanceM).toBe(16000)
    expect(view.totalAscentM).toBe(1800)
    expect(view.totalDescentM).toBe(900)
    expect(view.totalDurationH).toBe(5)
  })

  it('keeps a partner_betrieb endpoint', () => {
    const tour: RawTour = {
      tourId: 3, name: 'Mixed', numDays: 1,
      legs: [{ legIndex: 0, edgeId: 0, ...scalars(1000, 10, 20, 900, 900), from: { type: 'hut', id: 1 }, to: { type: 'partner_betrieb', id: 99 } }],
    }
    expect(buildOfficialTourViews([tour])[0].legs[0].to).toEqual({ type: 'partner_betrieb', id: 99 })
  })

  it('maps shipped leg anchors to lat/lng, null when a leg ships none', () => {
    const tour: RawTour = {
      tourId: 4, name: 'Anchored', numDays: 1,
      legs: [
        { legIndex: 0, edgeId: 0, ...scalars(1000, 0, 0, 900, 900), from: { type: 'hut', id: 1 }, to: { type: 'hut', id: 2 }, anchors: [[47, 11], [47.1, 11.1]] },
        { legIndex: 1, edgeId: 1, ...scalars(1000, 0, 0, 900, 900), from: { type: 'hut', id: 2 }, to: { type: 'hut', id: 3 } },
      ],
    }
    const [view] = buildOfficialTourViews([tour])
    expect(view.legs[0].anchors).toEqual([{ lat: 47, lng: 11 }, { lat: 47.1, lng: 11.1 }])
    expect(view.legs[1].anchors).toBeNull()
  })
})
