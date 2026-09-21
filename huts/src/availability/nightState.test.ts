import { describe, it, expect } from 'vitest'
import { classifyNight, nightText } from './nightState.js'
import type { HutDetail } from './types.js'

const detail = (status: string, free: number[]): HutDetail => ({
  hutId: 1, hutName: 'H',
  calendarDays: [{
    day: '10.07.2026', reservationMode: 'SERVICED', status,
    bedCategoriesData: free.map((totalFreePlaces) => ({ totalPlaces: 20, occupation: '', totalFreePlaces, label: '' })),
  }],
})

describe('classifyNight', () => {
  it('is unknown without detail (no OHRS id, failed fetch)', () => {
    expect(classifyNight(null, 2)).toEqual({ kind: 'unknown' })
  })
  it('is unknown for a technical error, distinct from full', () => {
    expect(classifyNight(detail('TECHNICAL_ERROR', []), 2)).toEqual({ kind: 'unknown' })
  })
  it('is full for closed / not reservable / zero free beds', () => {
    expect(classifyNight(detail('HUT_CLOSED_TO_PUBLIC', []), 2)).toEqual({ kind: 'full' })
    expect(classifyNight(detail('RESERVATION_NOT_POSSIBLE', []), 2)).toEqual({ kind: 'full' })
    expect(classifyNight(detail('AVAILABLE', [0, 0]), 2)).toEqual({ kind: 'full' })
  })
  it('sums free beds across categories and flags "few" below twice the party size', () => {
    expect(classifyNight(detail('AVAILABLE', [8, 4]), 2)).toEqual({ kind: 'free', places: 12 })
    expect(classifyNight(detail('AVAILABLE', [3]), 2)).toEqual({ kind: 'few', places: 3 })
    expect(classifyNight(detail('AVAILABLE', [4]), 2)).toEqual({ kind: 'free', places: 4 })
  })
  it('treats an unrecognised status with no bed data as unknown', () => {
    expect(classifyNight(detail('SOMETHING_NEW', []), 2)).toEqual({ kind: 'unknown' })
  })
})

describe('nightText', () => {
  it('uses the spec copy', () => {
    expect(nightText({ kind: 'free', places: 12 })).toBe('12 Plätze frei')
    expect(nightText({ kind: 'few', places: 3 })).toBe('3 Plätze frei')
    expect(nightText({ kind: 'few', places: 1 })).toBe('1 Platz frei')
    expect(nightText({ kind: 'full' })).toBe('ausgebucht')
    expect(nightText({ kind: 'unknown' })).toBe('Verfügbarkeit unbekannt – direkt anfragen')
  })
})
