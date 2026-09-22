/** Values the filter bar collects for a trip that does not exist yet; copied into the trip on pick. */
export interface TripDraft {
  /** ISO date of the first night, '' = undated. */
  startDate: string
  /** ISO date of the descent day, '' = undated. Ignored unless startDate is also set. */
  endDate: string
  partySize: number
  /** Day-count stepper, used only when startDate/endDate are unset. */
  dayCount: number
  /** "flexibel ±1 Tag" chip, used only when startDate/endDate are unset. */
  flexible: boolean
}

export const DEFAULT_DRAFT: TripDraft = { startDate: '', endDate: '', partySize: 1, dayCount: 3, flexible: false }

function daysBetween(fromIso: string, toIso: string): number {
  const [fy, fm, fd] = fromIso.split('-').map(Number)
  const [ty, tm, td] = toIso.split('-').map(Number)
  const from = Date.UTC(fy, fm - 1, fd)
  const to = Date.UTC(ty, tm - 1, td)
  return Math.round((to - from) / 86_400_000) + 1
}

/** The exact/target day count the ranking code aims for: from dates when set, else the stepper. */
export function dayCountFromDraft(draft: TripDraft): number {
  if (draft.startDate && draft.endDate) return daysBetween(draft.startDate, draft.endDate)
  return draft.dayCount
}

/** [min, max] days for the search query: exact when dated, else the stepper value widened by one
 *  day each way when "flexibel" is on (never below 2 days). */
export function legCountRangeFromDraft(draft: TripDraft): [number, number] {
  if (draft.startDate && draft.endDate) {
    const days = daysBetween(draft.startDate, draft.endDate)
    return [days, days]
  }
  if (!draft.flexible) return [draft.dayCount, draft.dayCount]
  return [Math.max(2, draft.dayCount - 1), draft.dayCount + 1]
}
