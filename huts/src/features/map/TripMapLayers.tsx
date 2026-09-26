import { Box, Button, Typography } from '@mui/material'
import type { TripLegs } from '@/trip/tripLegs.js'
import TripLayer from './TripLayer.js'
import type { CandidateMapMarker, TripEndMarker, TripHutMarker } from './TripLayer.js'
import { styles } from './TripMapLayers.styles.js'

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
    <Box sx={styles.statusBar}>
      <Typography variant="body2">{mode.activeLabel}</Typography>
      <Button size="small" onClick={mode.onCancelEditing}>Abbrechen</Button>
    </Box>
  )
}
