import type { Hub } from './types.js'

export interface TourListing {
  name: string
  legs: number[]
}

const legUrl = (tour: string, leg: number | 'restructure') => `/api/gpx/tours/${encodeURIComponent(tour)}/${leg}`

async function failure(res: Response): Promise<Error> {
  try {
    return new Error((await res.json()).error ?? `HTTP ${res.status}`)
  } catch {
    return new Error(`HTTP ${res.status}`)
  }
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw await failure(res)
  return res.json() as Promise<T>
}

export const getTours = () => getJson<TourListing[]>('/api/gpx/tours')
export const getHubs = () => getJson<Hub[]>('/api/gpx/hubs')
export const getConfig = () => getJson<{ maxSnapM: number }>('/api/gpx/config')

export async function getLeg(tour: string, leg: number): Promise<{ text: string; mtime: string }> {
  const res = await fetch(legUrl(tour, leg))
  if (!res.ok) throw await failure(res)
  return { text: await res.text(), mtime: res.headers.get('X-Gpx-Mtime') ?? '' }
}

export async function putLeg(
  tour: string, leg: number, text: string, mtime: string,
): Promise<{ ok: true; mtime: string } | { ok: false; conflict: true }> {
  const res = await fetch(legUrl(tour, leg), { method: 'PUT', headers: { 'If-Gpx-Mtime': mtime }, body: text })
  if (res.status === 409) return { ok: false, conflict: true }
  if (!res.ok) throw await failure(res)
  return { ok: true, mtime: (await res.json()).mtime }
}

export type LegSource = { from: number } | { text: string }

/** legs[i] becomes leg i+1 of the tour; `checks` maps leg number to the mtime the caller loaded. */
export async function restructureTour(
  tour: string, legs: LegSource[], checks: Record<number, string> = {},
): Promise<void> {
  const res = await fetch(legUrl(tour, 'restructure'), { method: 'POST', body: JSON.stringify({ legs, checks }) })
  if (!res.ok) throw await failure(res)
}
