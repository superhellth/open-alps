import { useEffect, useRef, useState } from 'react'
import type { MouseEvent, RefObject } from 'react'
import { Box, Typography } from '@mui/material'
import { tokens } from '@/ui/theme.js'
import { STOP_SYMBOL_SIZE, StopSymbol } from '@/ui/StopSymbol.js'
import type { StopMark } from '@/ui/StopSymbol.js'
import { fontSize, rem } from '@/ui/tokens.js'
import type { ProfilePosition } from '@/trip/tripLegs.js'
import {
  ELEVATION_LABEL_GAP, PROFILE_HEIGHT, STOP_SYMBOL_REACH, formatKm, fractionInLeg, legAtKm, makeScales, nearestPoint, profileCaption,
} from './profileScale.js'
import type { ElevationPoint, TripElevation } from './useTripElevation.js'
import { styles } from './HeightProfile.styles.js'

const FALLBACK_WIDTH = 600
const KM_LABEL_MIN_GAP_PX = 34
/** Below this vertical distance the min label would overlap the max label and is left out. */
const MIN_LABEL_SPACING_PX = 14
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

/** The whole trip as one elevation line over a baseline, split per leg so the hovered leg can be
 *  filled in signpost yellow. Every stop sits on the line as its map symbol, as on the stage rail, with its km
 *  below. A caption line above names start and destination, or reads out the cursor while hovering;
 *  the component keeps one height in every state. Hovering reports the leg and position along it. */
export default function HeightProfile({ elevation, stops, marks, highlightedLeg, onHoverLeg, onHoverPosition }: {
  elevation: TripElevation
  /** Names at the night boundaries: start, each hut, exit (legs + 1 entries). */
  stops: string[]
  /** Symbols at the night boundaries, parallel to `stops`. */
  marks: StopMark[]
  highlightedLeg: number | null
  onHoverLeg: (index: number | null) => void
  onHoverPosition: (position: ProfilePosition | null) => void
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const width = useWidth(rootRef)
  const [cursorKm, setCursorKm] = useState<number | null>(null)
  const { points, nightBoundariesKm: bounds } = elevation

  if (elevation.loading) {
    return (
      <Box ref={rootRef} sx={styles.root}>
        <Typography variant="caption" noWrap sx={styles.caption}>Höhenprofil lädt …</Typography>
        <Box sx={styles.plot} />
      </Box>
    )
  }
  if (points.length === 0) return <Box ref={rootRef} sx={styles.root} />

  const s = makeScales(points, bounds, width)
  const byLeg = new Map<number, ElevationPoint[]>()
  for (const p of points) {
    const list = byLeg.get(p.legIndex)
    if (list) list.push(p)
    else byLeg.set(p.legIndex, [p])
  }

  const linePoints = (pts: ElevationPoint[]) => pts.map((p) => `${s.x(p.distanceKm)},${s.y(p.elevationM)}`).join(' ')
  const highlighted = highlightedLeg === null ? undefined : byLeg.get(highlightedLeg)
  const highlightArea = highlighted
    && `${linePoints(highlighted)} ${s.x(highlighted[highlighted.length - 1].distanceKm)},${s.plotBottom} ${s.x(highlighted[0].distanceKm)},${s.plotBottom}`

  const cursorPoint = cursorKm === null ? null : nearestPoint(points, cursorKm)
  const cursorLeg = cursorKm === null ? null : legAtKm(bounds, cursorKm)

  const stopPoints = bounds.map((km) => ({ x: s.x(km), y: s.y(nearestPoint(points, km).elevationM) }))
  const extremes = s.y(s.minM) - s.y(s.maxM) < MIN_LABEL_SPACING_PX ? [s.maxM] : [s.maxM, s.minM]
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

  const caption = profileCaption(
    stops, cursorPoint && cursorLeg !== null && cursorKm !== null ? { km: cursorKm, elevationM: cursorPoint.elevationM, legIndex: cursorLeg } : null,
  )

  return (
    <Box ref={rootRef} sx={styles.root}>
      <Typography variant="caption" noWrap data-testid="profile-caption" sx={styles.caption}>{caption}</Typography>
      <svg data-testid="profile-svg" width={width} height={PROFILE_HEIGHT} onMouseMove={handleMove} onMouseLeave={handleLeave}>
        {extremes.map((m) => (
          <text key={m} data-testid="elevation-label" x={s.plotLeft - STOP_SYMBOL_REACH - ELEVATION_LABEL_GAP} y={s.y(m)} textAnchor="end" dominantBaseline="middle" fontSize={TEXT_SIZE} fill={tokens.ink}>
            {Math.round(m).toLocaleString('de-DE')}
          </text>
        ))}
        {highlightArea && <polygon data-testid={`leg-area-${highlightedLeg}`} points={highlightArea} fill={tokens.signpost} stroke="none" />}
        <line x1={s.plotLeft} x2={s.plotRight} y1={s.plotBottom} y2={s.plotBottom} stroke={tokens.ink} strokeWidth={1} />
        {[...byLeg.entries()].map(([legIndex, pts]) => {
          const on = legIndex === highlightedLeg
          return (
            <polyline
              key={legIndex} data-testid={`leg-segment-${legIndex}`} data-highlighted={on}
              points={linePoints(pts)}
              fill="none" stroke={tokens.ink} strokeWidth={on ? 2 : 1.5} strokeLinejoin="round"
            />
          )
        })}
        {stopPoints.slice(1, -1).map((d, i) => (
          <line key={i} data-testid="night-separator" x1={d.x} x2={d.x} y1={d.y} y2={s.plotBottom} stroke={tokens.ink} strokeWidth={1} />
        ))}
        {stopPoints.map((d, i) => marks[i] && (
          <g key={i} data-testid="stop-symbol">
            <StopSymbol mark={marks[i]} x={d.x - STOP_SYMBOL_SIZE / 2} y={d.y - STOP_SYMBOL_SIZE / 2} />
          </g>
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
