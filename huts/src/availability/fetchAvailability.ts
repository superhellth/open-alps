import { formatOhrsDate } from './formatDate.js'
import type { FreeByOffset } from './types.js'

const OHRS_URL = 'https://caa.alpenverein.at/service/server/callOHRS_REST.php'

// Keyed by the resolved date string (not the raw offset) + numOfPeople: two calls with the same
// offsetDays but different startDate resolve to different real-world nights and must not share a
// cache entry. Caches the in-flight Promise, not just the resolved value, so two concurrent
// fetchAvailabilityByOffset calls for the same night+party size still only fire one request.
const cache = new Map<string, Promise<Set<string> | 'unknown'>>()

async function fetchOneOffset(dateStr: string, numOfPeople: number): Promise<Set<string> | 'unknown'> {
  try {
    const res = await fetch(OHRS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ startDate: dateStr, numOfPeople, collectAll: true }),
    })
    if (!res.ok) return 'unknown'
    const ids: unknown = await res.json()
    if (!Array.isArray(ids)) return 'unknown'
    return new Set(ids.map((id) => String(id)))
  } catch {
    return 'unknown'
  }
}

export async function fetchAvailabilityByOffset(
  startDate: Date,
  numOfPeople: number,
  maxOffsetDays: number,
): Promise<FreeByOffset> {
  const offsets = Array.from({ length: maxOffsetDays }, (_, i) => i + 1)
  const entries = await Promise.all(
    offsets.map(async (offset) => {
      const dateStr = formatOhrsDate(startDate, offset)
      const cacheKey = `${dateStr}|${numOfPeople}`
      if (!cache.has(cacheKey)) cache.set(cacheKey, fetchOneOffset(dateStr, numOfPeople))
      return [offset, await cache.get(cacheKey)!] as const
    }),
  )
  return new Map(entries)
}
