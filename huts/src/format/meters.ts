/** Whole meters with German digit grouping, e.g. "2.340 m". */
export const formatMeters = (m: number) => `${Math.round(m).toLocaleString('de-DE')} m`
/** Ascent with its arrow, e.g. "↑ 2.340 m". */
export const formatAscent = (m: number) => `↑ ${formatMeters(m)}`
/** Descent with its arrow, e.g. "↓ 2.340 m". */
export const formatDescent = (m: number) => `↓ ${formatMeters(m)}`
