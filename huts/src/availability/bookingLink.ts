import { formatOhrsDate } from './formatDate.js'

/** German is the app's only UI language, matching hut-reservation.org's default (no lang= param
 *  needed — docs/alpenverein-api.md's "Booking deep link" section). */
export function buildBookingLink(ohrsHutId: string, date: Date): string {
  const dateFrom = formatOhrsDate(date, 0)
  const dateTo = formatOhrsDate(date, 1)
  return `https://www.hut-reservation.org/reservation/book-hut/${ohrsHutId}/wizard?dateFrom=${dateFrom}&dateTo=${dateTo}`
}
