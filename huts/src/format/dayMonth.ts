/** "12.07." for an ISO day (YYYY-MM-DD), read as UTC. */
export function formatDayMonth(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', timeZone: 'UTC' })
}

/** "12.07. – 16.07." */
export function formatDayMonthRange(startIso: string, endIso: string): string {
  return `${formatDayMonth(startIso)} – ${formatDayMonth(endIso)}`
}

/** ISO day shifted by `days`, UTC-safe. */
export function addIsoDays(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10)
}

/** Today as an ISO day, UTC. */
export function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

/** Whole days from ISO day `a` to ISO day `b` (negative when `b` is earlier). */
export function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000)
}
