import { SOURCE_TYPE_PARKING, SOURCE_TYPE_PARTNER, SOURCE_TYPE_STATION } from '../tourSearch/types.js'
import type { SourceType } from '../tourSearch/types.js'

export interface TripEndpoint {
  startId: number
  sourceType: SourceType
}

export interface TripVariant {
  sacCeiling: number | null
  allowUngraded: boolean
}

export interface Trip {
  id: string
  name: string
  createdAt: string
  updatedAt: string
  /** ISO date (YYYY-MM-DD) of the first night. */
  startDate: string | null
  /** 1-9, the OHRS bound. */
  partySize: number
  start: TripEndpoint
  /** Hut GUIDs in walking order; the only stable hut reference. */
  huts: string[]
  exit: TripEndpoint
  variant: TripVariant
}

export interface NewTripInput {
  name: string
  startDate: string | null
  partySize: number
  start: TripEndpoint
  huts: string[]
  exit: TripEndpoint
  variant: TripVariant
}

const SOURCE_TYPES: readonly number[] = [SOURCE_TYPE_STATION, SOURCE_TYPE_PARKING, SOURCE_TYPE_PARTNER]
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

export function newTrip(input: NewTripInput, now: Date = new Date(), id: string = crypto.randomUUID()): Trip {
  const iso = now.toISOString()
  return {
    id, name: input.name, createdAt: iso, updatedAt: iso,
    startDate: input.startDate, partySize: input.partySize,
    start: input.start, huts: [...input.huts], exit: input.exit, variant: input.variant,
  }
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function parseEndpoint(v: unknown): TripEndpoint | null {
  if (!isRecord(v)) return null
  if (typeof v.startId !== 'number' || !Number.isFinite(v.startId)) return null
  if (typeof v.sourceType !== 'number' || !SOURCE_TYPES.includes(v.sourceType)) return null
  return { startId: v.startId, sourceType: v.sourceType as SourceType }
}

/** Validates untrusted JSON (localStorage, share link, backup file). Null means "not a usable trip". */
export function parseTrip(value: unknown): Trip | null {
  if (!isRecord(value)) return null
  const { id, name, createdAt, updatedAt, startDate, partySize, huts, variant } = value
  if (typeof id !== 'string' || typeof name !== 'string') return null
  if (typeof createdAt !== 'string' || typeof updatedAt !== 'string') return null
  if (startDate !== null && (typeof startDate !== 'string' || !ISO_DATE.test(startDate))) return null
  if (typeof partySize !== 'number' || !Number.isInteger(partySize) || partySize < 1 || partySize > 25) return null
  if (!Array.isArray(huts) || !huts.every((h) => typeof h === 'string')) return null
  if (!isRecord(variant) || typeof variant.allowUngraded !== 'boolean') return null
  if (variant.sacCeiling !== null && typeof variant.sacCeiling !== 'number') return null
  const start = parseEndpoint(value.start)
  const exit = parseEndpoint(value.exit)
  if (!start || !exit) return null
  return {
    id, name, createdAt, updatedAt, startDate, partySize, start, exit,
    huts: huts as string[],
    variant: { sacCeiling: variant.sacCeiling as number | null, allowUngraded: variant.allowUngraded },
  }
}
