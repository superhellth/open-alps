/** DD.MM.YYYY, the date format every OHRS endpoint expects (docs/alpenverein-api.md).
 *  UTC-safe: adds offsetDays via Date.UTC arithmetic rather than local-time setDate, so a
 *  native <input type="date"> value (parsed as UTC midnight) never drifts a day from DST. */
export function formatOhrsDate(date: Date, offsetDays = 0): string {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + offsetDays))
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  return `${dd}.${mm}.${d.getUTCFullYear()}`
}
