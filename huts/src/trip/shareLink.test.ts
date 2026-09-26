import { describe, it, expect } from 'vitest'
import { decodeTripFromHash, encodeTripToHash, shareUrl, SHARE_HASH_PREFIX } from './shareLink.js'
import { newTrip } from './trip.js'

const trip = newTrip({
  name: 'Kaisertour – Süd', startDate: '2026-07-10', partySize: 3, start: { startId: 100, sourceType: 1 },
  huts: ['{593D0233-85B0-4086-B762-D4E94ED3B2CF}', '{B}'], exit: { startId: 101, sourceType: 1 },
  variant: { sacCeiling: 3, allowUngraded: true }, source: { kind: 'official' as const, tourId: 4 },
}, new Date('2026-06-01T00:00:00Z'), 'orig')

describe('share link', () => {
  it('round-trips the itinerary, including non-ASCII names', () => {
    const hash = encodeTripToHash(trip)
    expect(hash.startsWith(SHARE_HASH_PREFIX)).toBe(true)
    expect(hash.slice(SHARE_HASH_PREFIX.length)).not.toMatch(/[+/=\s]/) // URL-safe payload
    const back = decodeTripFromHash(hash, new Date('2026-07-01T00:00:00Z'), 'copy')!
    expect(back).toMatchObject({
      id: 'copy', name: 'Kaisertour – Süd', startDate: '2026-07-10', partySize: 3, huts: trip.huts,
      start: trip.start, exit: trip.exit, variant: trip.variant, source: trip.source,
    })
    expect(back.createdAt).toBe('2026-07-01T00:00:00.000Z')
  })
  it('rejects anything that is not a valid share hash', () => {
    expect(decodeTripFromHash('#admin')).toBeNull()
    expect(decodeTripFromHash('#trip=')).toBeNull()
    expect(decodeTripFromHash('#trip=%%%')).toBeNull()
    expect(decodeTripFromHash(`#trip=${btoa('{"v":1,"t":{"x":1}}')}`)).toBeNull()
  })
  it('builds an absolute url', () => {
    expect(shareUrl(trip, { origin: 'https://example.org', pathname: '/' })).toMatch(/^https:\/\/example\.org\/#trip=/)
  })
})
