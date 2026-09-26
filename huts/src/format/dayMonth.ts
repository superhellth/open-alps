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
