/** Tour length as shown in the results list and on tour boards, e.g. "42.3 km". */
export function formatDistanceKm(meters: number): string {
  return `${(meters / 1000).toFixed(1)} km`
}
