import { describe, it, expect } from 'vitest'
import { newTrip, parseTrip, shiftStartDate } from './trip.js'

const input = {
  name: 'Testtour', startDate: '2026-07-10', partySize: 2,
  start: { startId: 100, sourceType: 1 as const }, huts: ['{A}', '{B}'],
  exit: { startId: 100, sourceType: 1 as const },
  variant: { sacCeiling: 3, allowUngraded: true },
}

describe('newTrip', () => {
  it('fills id/timestamps and one open night per hut', () => {
    const t = newTrip(input, new Date('2026-06-01T10:00:00Z'), 'id-1')
    expect(t.id).toBe('id-1')
    expect(t.createdAt).toBe('2026-06-01T10:00:00.000Z')
    expect(t.updatedAt).toBe(t.createdAt)
    expect(t.nights).toEqual([{ status: 'open' }, { status: 'open' }])
  })
})

describe('parseTrip', () => {
  const good = newTrip(input, new Date('2026-06-01T10:00:00Z'), 'id-1')
  it('round-trips a valid trip through JSON', () => {
    expect(parseTrip(JSON.parse(JSON.stringify(good)))).toEqual(good)
  })
  it('rejects non-objects, missing fields and a nights/huts length mismatch', () => {
    expect(parseTrip(null)).toBeNull()
    expect(parseTrip({ ...good, huts: 'x' })).toBeNull()
    expect(parseTrip({ ...good, nights: [{ status: 'open' }] })).toBeNull()
    expect(parseTrip({ ...good, nights: [{ status: 'nope' }, { status: 'open' }] })).toBeNull()
    expect(parseTrip({ ...good, start: { startId: 'x', sourceType: 1 } })).toBeNull()
  })
  it('rejects a party size outside 1-9 and a malformed date', () => {
    expect(parseTrip({ ...good, partySize: 0 })).toBeNull()
    expect(parseTrip({ ...good, partySize: 10 })).toBeNull()
    expect(parseTrip({ ...good, startDate: '10.07.2026' })).toBeNull()
  })
  it('accepts a null start date', () => {
    expect(parseTrip({ ...good, startDate: null })?.startDate).toBeNull()
  })
})

describe('shiftStartDate', () => {
  it('moves the first night by whole days, month boundaries included', () => {
    const t = newTrip({ ...input, startDate: '2026-07-31' }, new Date(), 'id')
    expect(shiftStartDate(t, 1).startDate).toBe('2026-08-01')
    expect(shiftStartDate(t, -1).startDate).toBe('2026-07-30')
  })
  it('leaves an undated trip undated', () => {
    const t = newTrip({ ...input, startDate: null }, new Date(), 'id')
    expect(shiftStartDate(t, 1).startDate).toBeNull()
  })
})
