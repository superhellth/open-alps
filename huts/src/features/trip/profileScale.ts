import { formatMeters } from '@/format/meters.js'
import { STOP_SYMBOL_SIZE } from '@/ui/StopSymbol.js'
import type { ElevationPoint } from './useTripElevation.js'

export const PROFILE_HEIGHT = 140
/** How far a stop symbol reaches past its centre. */
export const STOP_SYMBOL_REACH = STOP_SYMBOL_SIZE / 2
/** Gap between the elevation labels and the reach of the start symbol. */
export const ELEVATION_LABEL_GAP = 4
/** Room for the min/max elevation labels (left, clear of the start symbol), the stop symbols (top, right) and km labels (bottom). */
export const PROFILE_MARGINS = {
  left: 36 + ELEVATION_LABEL_GAP + STOP_SYMBOL_REACH, right: STOP_SYMBOL_REACH, top: STOP_SYMBOL_REACH, bottom: 22,
}

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

export interface ProfileHover {
  km: number
  elevationM: number
  legIndex: number
}

/** The line above the chart: the trip's start and destination while idle; while hovering, the
 *  cursor's km and elevation, then its stage and the stops that stage runs between. */
export function profileCaption(stops: string[], hover: ProfileHover | null): string {
  if (!hover) return `${stops[0] ?? ''} → ${stops.at(-1) ?? ''}`
  const { km, elevationM, legIndex } = hover
  const stage = legIndex === stops.length - 2 ? 'Abstieg' : `Etappe ${legIndex + 1}`
  return `km ${formatKm(km)} · ${formatMeters(elevationM)} · ${stage}: ${stops[legIndex] ?? ''} → ${stops[legIndex + 1] ?? ''}`
}

export const formatKm = (km: number) => km.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
