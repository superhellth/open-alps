import type { ElevationPoint } from './useTripElevation.js'

export const PROFILE_HEIGHT = 140
/** Room for the min/max elevation labels (left), stop names (top) and km labels (bottom). */
export const PROFILE_MARGINS = { left: 40, right: 8, top: 18, bottom: 22 }

export interface ElevationAxis {
  lo: number
  hi: number
}

/** Axis limits padded to whole steps of 500 m, or 250 m when the elevation span is under 1000 m. */
export function elevationAxis(minM: number, maxM: number): ElevationAxis {
  const step = maxM - minM < 1000 ? 250 : 500
  const lo = Math.floor(minM / step) * step
  let hi = Math.ceil(maxM / step) * step
  if (hi === lo) hi = lo + step
  return { lo, hi }
}

export interface ProfileScales {
  x: (km: number) => number
  y: (elevationM: number) => number
  /** Pixel x (relative to the svg) to km, clamped to the plot. */
  kmAt: (px: number) => number
  plotLeft: number
  plotRight: number
  plotTop: number
  plotBottom: number
  axis: ElevationAxis
  maxKm: number
  /** Lowest and highest sample of the trip. */
  minM: number
  maxM: number
}

export function makeScales(
  points: ElevationPoint[], boundariesKm: number[], width: number, height = PROFILE_HEIGHT,
): ProfileScales {
  const plotLeft = PROFILE_MARGINS.left
  const plotRight = width - PROFILE_MARGINS.right
  const plotTop = PROFILE_MARGINS.top
  const plotBottom = height - PROFILE_MARGINS.bottom
  const maxKm = Math.max(boundariesKm.at(-1) ?? 0, points.at(-1)?.distanceKm ?? 0) || 1
  let min = Infinity
  let max = -Infinity
  for (const p of points) {
    if (p.elevationM < min) min = p.elevationM
    if (p.elevationM > max) max = p.elevationM
  }
  const axis = elevationAxis(min, max)
  const plotW = Math.max(1, plotRight - plotLeft)
  return {
    x: (km) => plotLeft + (km / maxKm) * plotW,
    y: (ele) => plotBottom - ((ele - axis.lo) / (axis.hi - axis.lo)) * (plotBottom - plotTop),
    kmAt: (px) => Math.min(1, Math.max(0, (px - plotLeft) / plotW)) * maxKm,
    plotLeft, plotRight, plotTop, plotBottom, axis, maxKm, minM: min, maxM: max,
  }
}

/** Index of the leg containing `km`; a zero-length leg (no elevation data) is never returned, the last leg owns the very end. */
export function legAtKm(boundariesKm: number[], km: number): number {
  const legCount = boundariesKm.length - 1
  for (let i = 0; i < legCount; i++) if (km < boundariesKm[i + 1]) return i
  return Math.max(0, legCount - 1)
}

export function fractionInLeg(boundariesKm: number[], legIndex: number, km: number): number {
  const start = boundariesKm[legIndex]
  const end = boundariesKm[legIndex + 1]
  return end > start ? Math.min(1, Math.max(0, (km - start) / (end - start))) : 0
}

export function nearestPoint(points: ElevationPoint[], km: number): ElevationPoint {
  return points.reduce((best, p) => (Math.abs(p.distanceKm - km) < Math.abs(best.distanceKm - km) ? p : best))
}

/** Cuts `text` to fit `widthPx` at an average glyph width of `charPx`, ending in "…"; '' when nothing fits. */
export function truncateLabel(text: string, widthPx: number, charPx = 6.5): string {
  const max = Math.floor(widthPx / charPx)
  if (text.length <= max) return text
  if (max <= 1) return ''
  return `${text.slice(0, max - 1)}…`
}

export interface StopLabel {
  x: number
  text: string
}

/** Stop labels centred on their night lines at `xs`. Each label owns the space up to halfway to its
 *  neighbours. A hut name that does not fit there falls back to its stage number, or '' when that
 *  does not fit either. The start and exit names shift inwards to stay inside `width` and are
 *  ellipsized to their space. */
export function placeStopLabels(xs: number[], names: string[], width: number, charPx = 6.5, gapPx = 6): StopLabel[] {
  const last = xs.length - 1
  return xs.map((x, i) => {
    const lo = i === 0 ? 0 : (xs[i - 1] + x) / 2 + gapPx / 2
    const hi = i === last ? width : (x + xs[i + 1]) / 2 - gapPx / 2
    if (i === 0 || i === last) {
      const text = truncateLabel(names[i] ?? '', hi - lo, charPx)
      const half = (text.length * charPx) / 2
      return { x: Math.min(hi - half, Math.max(lo + half, x)), text }
    }
    const text = [names[i] ?? '', String(i)].find((t) => x - (t.length * charPx) / 2 >= lo && x + (t.length * charPx) / 2 <= hi) ?? ''
    return { x, text }
  })
}

export const formatKm = (km: number) => km.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
