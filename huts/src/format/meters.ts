/** Whole meters with German digit grouping, e.g. "2.340 m". */
export const formatMeters = (m: number) => `${Math.round(m).toLocaleString('de-DE')} m`
