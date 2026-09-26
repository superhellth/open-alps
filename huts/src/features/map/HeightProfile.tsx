import { useEffect, useRef, useState } from 'react'
import type { MouseEvent, RefObject } from 'react'
import { Box, Typography } from '@mui/material'
import { alpha } from '@mui/material/styles'
import { formatMeters } from '@/format/meters.js'
import { tokens } from '@/ui/theme.js'
import { fontSize, opacity, rem } from '@/ui/tokens.js'
import { PROFILE_HEIGHT, formatKm, fractionInLeg, legAtKm, makeScales, nearestPoint, truncateLabel } from './profileScale.js'
import type { ProfilePosition } from './types.js'
import type { ElevationPoint, TripElevation } from './useTripElevation.js'
import { styles } from './HeightProfile.styles.js'

const FALLBACK_WIDTH = 600
const LABEL_GAP_PX = 6
const KM_LABEL_MIN_GAP_PX = 34
const TEXT_SIZE = rem(fontSize.xs)

/** Width of `ref`'s element, kept current with a ResizeObserver; the fallback stands in where layout is unavailable. */
function useWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(FALLBACK_WIDTH)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => {
      const w = el.getBoundingClientRect().width
      if (w > 0) setWidth(w)
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [ref])
  return width
}

/** The whole trip as one filled elevation curve, split per leg so the hovered leg can be filled in
 *  signpost yellow. Night boundaries carry the stop names and km; hovering shows a cursor with a
 *  readout and reports the leg and position along it. */
export default function HeightProfile({ elevation, stops, highlightedLeg, onHoverLeg, onHoverPosition }: {
  elevation: TripElevation
  /** Names at the night boundaries: start, each hut, exit (legs + 1 entries). */
  stops: string[]
  highlightedLeg: number | null
  onHoverLeg: (index: number | null) => void
  onHoverPosition: (position: ProfilePosition | null) => void
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const width = useWidth(rootRef)
  const [cursorKm, setCursorKm] = useState<number | null>(null)
  const { points, nightBoundariesKm: bounds } = elevation

  if (elevation.loading) {
    return <Box ref={rootRef} sx={styles.root}><Typography variant="body2" sx={styles.message}>Höhenprofil lädt …</Typography></Box>
  }
  if (points.length === 0) return <Box ref={rootRef} sx={styles.root} />

  const s = makeScales(points, bounds, width)
  const exitLeg = bounds.length - 2
  const byLeg = new Map<number, ElevationPoint[]>()
  for (const p of points) {
    const list = byLeg.get(p.legIndex)
    if (list) list.push(p)
    else byLeg.set(p.legIndex, [p])
  }

  const cursorPoint = cursorKm === null ? null : nearestPoint(points, cursorKm)
  const cursorLeg = cursorKm === null ? null : legAtKm(bounds, cursorKm)

  const stopLabels = bounds.map((km, i) => {
    const last = i === bounds.length - 1
    const x = s.x(km)
    const neighbourX = last ? s.x(bounds[i - 1] ?? km) : s.x(bounds[i + 1])
    return {
      i, x: last ? x - 3 : x + 3, anchor: last ? ('end' as const) : ('start' as const),
      text: truncateLabel(stops[i] ?? '', Math.abs(neighbourX - x) - LABEL_GAP_PX),
    }
  })
  let lastKmX = -Infinity
  const kmLabels = bounds.flatMap((km, i) => {
    const x = s.x(km)
    if (x - lastKmX < KM_LABEL_MIN_GAP_PX) return []
    lastKmX = x
    const anchor = i === 0 ? ('start' as const) : i === bounds.length - 1 ? ('end' as const) : ('middle' as const)
    return [{ i, x, anchor, text: formatKm(km) }]
  })

  function handleMove(e: MouseEvent<SVGSVGElement>) {
    const km = s.kmAt(e.clientX - e.currentTarget.getBoundingClientRect().left)
    const legIndex = legAtKm(bounds, km)
    setCursorKm(km)
    onHoverLeg(legIndex)
    onHoverPosition({ legIndex, fraction: fractionInLeg(bounds, legIndex, km) })
  }
  function handleLeave() {
    setCursorKm(null)
    onHoverLeg(null)
    onHoverPosition(null)
  }

  const readout = cursorPoint && cursorLeg !== null && cursorKm !== null
    ? `km ${formatKm(cursorKm)} · ${formatMeters(cursorPoint.elevationM)} · ${cursorLeg === exitLeg ? 'Abstieg' : `Etappe ${cursorLeg + 1}`}`
    : ' '

  return (
    <Box ref={rootRef} sx={styles.root}>
      <Typography variant="caption" sx={styles.readout}>{readout}</Typography>
      <svg data-testid="profile-svg" width={width} height={PROFILE_HEIGHT} onMouseMove={handleMove} onMouseLeave={handleLeave}>
        {s.axis.ticks.map((tick) => (
          <g key={tick}>
            <line
              data-testid="grid-line" x1={s.plotLeft} x2={s.plotRight} y1={s.y(tick)} y2={s.y(tick)}
              stroke={alpha(tokens.ink, opacity.outline)} strokeWidth={1}
            />
            <text x={s.plotLeft - 4} y={s.y(tick)} textAnchor="end" dominantBaseline="middle" fontSize={TEXT_SIZE} fill={tokens.ink}>
              {tick.toLocaleString('de-DE')}
            </text>
          </g>
        ))}
        {[...byLeg.entries()].map(([legIndex, pts]) => {
          const on = legIndex === highlightedLeg
          const line = pts.map((p) => `${s.x(p.distanceKm)},${s.y(p.elevationM)}`)
          const area = `${line.join(' ')} ${s.x(pts[pts.length - 1].distanceKm)},${s.plotBottom} ${s.x(pts[0].distanceKm)},${s.plotBottom}`
          return (
            <g key={legIndex}>
              <polygon
                data-testid={`leg-area-${legIndex}`} data-highlighted={on} points={area}
                fill={on ? tokens.signpost : alpha(tokens.ink, opacity.shadow)} stroke="none"
              />
              <polyline
                data-testid={`leg-segment-${legIndex}`} data-highlighted={on} points={line.join(' ')}
                fill="none" stroke={tokens.ink} strokeWidth={on ? 2 : 1.5}
              />
            </g>
          )
        })}
        {bounds.slice(1, -1).map((km, i) => (
          <line
            key={i} data-testid="night-separator" x1={s.x(km)} x2={s.x(km)} y1={s.plotTop} y2={s.plotBottom}
            stroke={tokens.ink} strokeWidth={1}
          />
        ))}
        {stopLabels.map((l) => (
          <text key={l.i} data-testid="stop-label" x={l.x} y={s.plotTop - 6} textAnchor={l.anchor} fontSize={TEXT_SIZE} fontWeight={600} fill={tokens.ink}>
            {l.text}
          </text>
        ))}
        {kmLabels.map((l) => (
          <text key={l.i} data-testid="km-label" x={l.x} y={PROFILE_HEIGHT - 6} textAnchor={l.anchor} fontSize={TEXT_SIZE} fill={tokens.ink}>
            {l.text}
          </text>
        ))}
        {cursorPoint && (
          <g pointerEvents="none">
            <line x1={s.x(cursorPoint.distanceKm)} x2={s.x(cursorPoint.distanceKm)} y1={s.plotTop} y2={s.plotBottom} stroke={tokens.ink} strokeWidth={1} />
            <circle
              data-testid="profile-cursor" cx={s.x(cursorPoint.distanceKm)} cy={s.y(cursorPoint.elevationM)} r={4}
              fill={tokens.white} stroke={tokens.ink} strokeWidth={2}
            />
          </g>
        )}
      </svg>
    </Box>
  )
}
