import { useState } from 'react'
import { Box, Button, Collapse, Typography } from '@mui/material'
import type { TripLegs } from '@/trip/tripLegs.js'
import HeightProfile from './HeightProfile.js'
import TripLayer from './TripLayer.js'
import type { CandidateMapMarker, TripEndMarker, TripHutMarker } from './TripLayer.js'
import { useTripElevation } from './useTripElevation.js'

export interface TripMapMode {
  kind: 'trip'
  tripLegs: TripLegs
  tripHuts: TripHutMarker[]
  tripEnds: TripEndMarker[]
  /** Swap/extend/start/exit candidates of the active edit, drawn as signposts. */
  candidates: CandidateMapMarker[]
  hutCoordsById: Map<number, { lat: number; lng: number }>
  candidateStartCoords: Map<number, { lat: number; lng: number }>
  /** Set while an edit waits for a pick on the map. */
  activeLabel: string | null
  onPickCandidate: (arg: { hutIndex?: number; startId?: number }) => void
  onCancelEditing: () => void
  onHoverLeg: (index: number | null) => void
}

/** Markers inside the map. */
export function TripMapLayers({ mode }: { mode: TripMapMode }) {
  return (
    <TripLayer
      tripHuts={mode.tripHuts} tripEnds={mode.tripEnds} candidates={mode.candidates}
      hutCoordsById={mode.hutCoordsById} candidateStartCoords={mode.candidateStartCoords} onPickCandidate={mode.onPickCandidate}
    />
  )
}

/** Floating "active label + Abbrechen" bar over the map while an edit is active. */
export function TripMapStatusBar({ mode }: { mode: TripMapMode }) {
  if (!mode.activeLabel) return null
  return (
    <Box sx={{ position: 'absolute', top: 8, left: '50%', transform: 'translateX(-50%)', zIndex: 1000, bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: 1, px: 1.5, py: 0.5, display: 'flex', gap: 1, alignItems: 'center' }}>
      <Typography variant="body2">{mode.activeLabel}</Typography>
      <Button size="small" onClick={mode.onCancelEditing}>Abbrechen</Button>
    </Box>
  )
}

/** Collapsible height profile docked below the map. Elevation loads only while a trip is open. */
export function TripMapProfile({ mode, highlightedLeg }: { mode: TripMapMode; highlightedLeg: number | null }) {
  const elevation = useTripElevation(mode.tripLegs)
  const [open, setOpen] = useState(true)
  return (
    <Box sx={{ borderTop: '1px solid', borderColor: 'divider' }}>
      <Button size="small" onClick={() => setOpen((o) => !o)} sx={{ width: '100%', justifyContent: 'space-between' }}>
        Höhenprofil {open ? '▾' : '▸'}
      </Button>
      <Collapse in={open}>
        <HeightProfile elevation={elevation} highlightedLeg={highlightedLeg} onHoverLeg={mode.onHoverLeg} onHoverPosition={() => {}} />
      </Collapse>
    </Box>
  )
}
