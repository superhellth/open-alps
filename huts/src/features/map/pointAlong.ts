const segmentLength = (a: [number, number], b: [number, number]) => Math.hypot(b[0] - a[0], b[1] - a[1])

/** The point at `fraction` (clamped to 0..1) of the polyline's cumulative planar length, in the
 *  polyline's own direction. Planar (degrees, no projection): it only positions a cursor dot. */
export function pointAlong(coords: [number, number][], fraction: number): [number, number] {
  if (coords.length === 0) throw new Error('pointAlong needs at least one coordinate')
  const lengths = coords.slice(1).map((c, i) => segmentLength(coords[i], c))
  const total = lengths.reduce((sum, l) => sum + l, 0)
  if (total === 0) return coords[0]
  let remaining = Math.min(1, Math.max(0, fraction)) * total
  for (let i = 0; i < lengths.length; i++) {
    if (remaining <= lengths[i]) {
      const t = lengths[i] === 0 ? 0 : remaining / lengths[i]
      const [a, b] = [coords[i], coords[i + 1]]
      return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
    }
    remaining -= lengths[i]
  }
  return coords[coords.length - 1]
}
