import type { MouseEvent } from 'react'
import { Box, Typography } from '@mui/material'
import { tokens } from '@/ui/theme.js'
import type { TripElevation } from './useTripElevation.js'

const WIDTH = 600
const HEIGHT = 100
const PAD_TOP = 8
const PAD_BOTTOM = 4

function scales(elevation: TripElevation) {
  const maxKm = elevation.points.at(-1)?.distanceKm ?? 1
  const elevations = elevation.points.map((p) => p.elevationM)
  const minEle = Math.min(...elevations)
  const maxEle = Math.max(...elevations)
  const eleSpan = Math.max(1, maxEle - minEle)
  const x = (km: number) => (km / maxKm) * WIDTH
  const y = (ele: number) => PAD_TOP + (1 - (ele - minEle) / eleSpan) * (HEIGHT - PAD_TOP - PAD_BOTTOM)
  return { x, y, maxKm }
}

/** One continuous filled line for the whole trip, split into per-leg segments so a leg can be
 *  highlighted independently; thin verticals mark each interior night boundary (not the trip's
 *  own start/exit ends). */
export default function HeightProfile({ elevation, highlightedLeg, onHoverLeg, onHoverPosition }: {
  elevation: TripElevation
  highlightedLeg: number | null
  onHoverLeg: (index: number | null) => void
  onHoverPosition: (point: { distanceKm: number } | null) => void
}) {
  if (elevation.loading) {
    return <Typography variant="body2" sx={{ p: 1 }}>Höhenprofil lädt …</Typography>
  }
  if (elevation.points.length === 0) return null

  const { x, y, maxKm } = scales(elevation)
  const segments = new Map<number, { distanceKm: number; elevationM: number }[]>()
  for (const p of elevation.points) {
    if (!segments.has(p.legIndex)) segments.set(p.legIndex, [])
    segments.get(p.legIndex)!.push(p)
  }

  function handleMove(e: MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect()
    const fraction = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width))
    const distanceKm = fraction * maxKm
    const nearest = elevation.points.reduce((best, p) =>
      Math.abs(p.distanceKm - distanceKm) < Math.abs(best.distanceKm - distanceKm) ? p : best)
    onHoverLeg(nearest.legIndex)
    onHoverPosition({ distanceKm })
  }
  function handleLeave() {
    onHoverLeg(null)
    onHoverPosition(null)
  }

  return (
    <Box sx={{ width: '100%', bgcolor: 'background.paper' }}>
      <svg
        data-testid="profile-svg" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width="100%" height={HEIGHT}
        preserveAspectRatio="none" onMouseMove={handleMove} onMouseLeave={handleLeave}
      >
        {[...segments.entries()].map(([legIndex, pts]) => (
          <polyline
            key={legIndex} data-testid={`leg-segment-${legIndex}`} data-highlighted={legIndex === highlightedLeg}
            points={pts.map((p) => `${x(p.distanceKm)},${y(p.elevationM)}`).join(' ')}
            fill="none" stroke={legIndex === highlightedLeg ? tokens.signpost : tokens.ink}
            strokeWidth={legIndex === highlightedLeg ? 3 : 1.5}
          />
        ))}
        {elevation.nightBoundariesKm.slice(1, -1).map((km, i) => (
          <line
            key={i} data-testid="night-separator"
            x1={x(km)} x2={x(km)} y1={PAD_TOP} y2={HEIGHT - PAD_BOTTOM}
            stroke={tokens.ink} strokeWidth={1} strokeDasharray="2 2"
          />
        ))}
      </svg>
    </Box>
  )
}
