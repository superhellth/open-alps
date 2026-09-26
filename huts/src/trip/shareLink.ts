import { parseTrip } from './trip.js'
import type { Trip } from './trip.js'

export const SHARE_HASH_PREFIX = '#trip='

function toBase64Url(text: string): string {
  const bytes = new TextEncoder().encode(text)
  let binary = ''
  bytes.forEach((b) => { binary += String.fromCharCode(b) })
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function fromBase64Url(text: string): string {
  const padded = text.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(text.length / 4) * 4, '=')
  const binary = atob(padded)
  return new TextDecoder().decode(Uint8Array.from(binary, (c) => c.charCodeAt(0)))
}

/** The itinerary only: id and timestamps stay behind. */
export function encodeTripToHash(trip: Trip): string {
  const { id: _id, createdAt: _c, updatedAt: _u, ...itinerary } = trip
  return SHARE_HASH_PREFIX + toBase64Url(JSON.stringify({ v: 1, t: itinerary }))
}

export function decodeTripFromHash(hash: string, now: Date = new Date(), id: string = crypto.randomUUID()): Trip | null {
  if (!hash.startsWith(SHARE_HASH_PREFIX) || hash.length === SHARE_HASH_PREFIX.length) return null
  try {
    const payload = JSON.parse(fromBase64Url(hash.slice(SHARE_HASH_PREFIX.length)))
    if (payload?.v !== 1 || typeof payload.t !== 'object' || payload.t === null) return null
    const iso = now.toISOString()
    return parseTrip({ ...payload.t, id, createdAt: iso, updatedAt: iso })
  } catch {
    return null
  }
}

export function shareUrl(trip: Trip, location: Pick<Location, 'origin' | 'pathname'>): string {
  return `${location.origin}${location.pathname}${encodeTripToHash(trip)}`
}
