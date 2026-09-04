import { formatOhrsDate } from './formatDate.js'
import type { HutDetail } from './types.js'

const OHRS_URL = 'https://caa.alpenverein.at/service/server/callOHRS_REST.php'

interface OhrsBedCategoryLanguageRaw {
  language: string
  label: string
  shortLabel: string
}

interface OhrsBedCategoryRaw {
  totalPlaces: number
  occupation: string
  totalFreePlaces: number
  hutBedCategoryLanguagesData: OhrsBedCategoryLanguageRaw[]
}

interface OhrsCalendarDayRaw {
  day: string
  reservationMode: string
  status: string
  bedCategoriesData: OhrsBedCategoryRaw[]
}

interface OhrsHutAvailabilityRaw {
  hutID: number
  hutName: string
  calendarDays: OhrsCalendarDayRaw[]
}

interface OhrsDetailResponseRaw {
  hutsAvailability: OhrsHutAvailabilityRaw[]
}

const cache = new Map<string, Promise<HutDetail>>()

function technicalErrorDetail(ohrsHutId: string, dateStr: string): HutDetail {
  return {
    hutId: Number(ohrsHutId), hutName: '',
    calendarDays: [{ day: dateStr, reservationMode: '', status: 'TECHNICAL_ERROR', bedCategoriesData: [] }],
  }
}

function toHutDetail(raw: OhrsHutAvailabilityRaw): HutDetail {
  return {
    hutId: raw.hutID,
    hutName: raw.hutName,
    calendarDays: raw.calendarDays.map((day) => ({
      day: day.day,
      reservationMode: day.reservationMode,
      status: day.status,
      bedCategoriesData: day.bedCategoriesData.map((bc) => ({
        totalPlaces: bc.totalPlaces,
        occupation: bc.occupation,
        totalFreePlaces: bc.totalFreePlaces,
        label: bc.hutBedCategoryLanguagesData.find((l) => l.language === 'DE_DE')?.label ?? '',
      })),
    })),
  }
}

async function fetchOneDetail(
  ohrsHutId: string, tenantCode: number, dateStr: string, endDateStr: string, numOfPeople: number,
): Promise<HutDetail> {
  try {
    const res = await fetch(OHRS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        startDate: dateStr, endDate: endDateStr, huts: [ohrsHutId],
        numOfPeople: String(numOfPeople), onlyAvailablePlaces: false, page: 0, tenantCode,
      }),
    })
    if (!res.ok) return technicalErrorDetail(ohrsHutId, dateStr)
    const data: OhrsDetailResponseRaw[] = await res.json()
    const raw = data[0]?.hutsAvailability?.[0]
    if (!raw) return technicalErrorDetail(ohrsHutId, dateStr)
    return toHutDetail(raw)
  } catch {
    return technicalErrorDetail(ohrsHutId, dateStr)
  }
}

/** One night = startDate/endDate = date/date+1, matching this app's one-leg-one-night model
 *  (docs/superpowers/specs/2026-09-01-hut-availability-routing-design.md §3). Never call this in
 *  a loop over more than one already-expanded tour's huts — one request per hut, per night. */
export function fetchHutDetail(
  ohrsHutId: string, tenantCode: number, date: Date, numOfPeople: number,
): Promise<HutDetail> {
  const dateStr = formatOhrsDate(date, 0)
  const endDateStr = formatOhrsDate(date, 1)
  const cacheKey = `${ohrsHutId}|${dateStr}|${numOfPeople}`
  if (!cache.has(cacheKey)) cache.set(cacheKey, fetchOneDetail(ohrsHutId, tenantCode, dateStr, endDateStr, numOfPeople))
  return cache.get(cacheKey)!
}
