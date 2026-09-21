const FRACTION: Record<number, string> = { 0: '', 1: '¼', 2: '½', 3: '¾' }

/** Signpost style: rounded to the quarter hour, vulgar fractions, never "3:30 h". */
export function formatSignpostTime(hours: number): string {
  const quarters = Math.round(hours * 4)
  const whole = Math.floor(quarters / 4)
  const fraction = FRACTION[quarters % 4]
  if (whole === 0 && fraction) return `${fraction} Std`
  return `${whole}${fraction} Std`
}
