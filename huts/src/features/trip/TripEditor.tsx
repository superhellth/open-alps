import { useState } from 'react'
import type { MouseEvent, ReactNode } from 'react'
import { Box, Button, IconButton, Menu, MenuItem, Typography } from '@mui/material'
import { formatSignpostTime } from '@/format/signpostTime.js'
import {
  applyEndpoint, applyExtend, applySwap, applyTrim, endpointCandidates, extendCandidates,
  modeOfTrip, swapCandidates, trimAllowed,
} from '@/trip/tripEdit.js'
import type { EndpointCandidate } from '@/trip/tripEdit.js'
import type { TripLegs } from '@/trip/tripLegs.js'
import type { TripGraph } from '@/tourSearch/types.js'
import type { SourceType } from '@/tourSearch/types.js'
import type { Trip } from '@/trip/trip.js'
import { styles } from './TripEditor.styles.js'

export type EditingState =
  | { kind: 'swap'; index: number }
  | { kind: 'extend'; side: 'first' | 'last' }
  | { kind: 'start' }
  | { kind: 'exit' }
  | null

export interface CandidateMarker {
  /** Set for a hut candidate (swap/extend). */
  hutIndex?: number
  /** Set for a start-point candidate (start/exit). */
  startId?: number
  sourceType?: SourceType
  legInH?: number
  legOutH?: number
  legH?: number
}

export interface TripEditorProps {
  graph: TripGraph
  trip: Trip | null
  tripLegs: TripLegs | null
  hutNameById: Map<number, string>
  startLabel: (startId: number) => string
  editing: EditingState
  onEditing: (editing: EditingState) => void
  onChange: (trip: Trip) => void
}

const ACTIVE_LABEL = {
  swap: (index: number) => `Neue Hütte für Etappe ${index + 1} wählen`,
  extend: () => 'Nächste Hütte wählen',
  start: () => 'Neuen Start wählen',
  exit: () => 'Neues Ziel wählen',
}

/** All trip edits are moves inside the routing graph (tourSearch/tripEdit.ts); this only renders
 *  them and forwards the chosen move. Candidates render both as map markers (the caller places
 *  them via `candidates`/`pickCandidate`) and as buttons in the panel, so every edit works without
 *  the map. */
export function useTripEditor({ graph, trip, tripLegs, hutNameById, startLabel, editing, onEditing, onChange }: TripEditorProps) {
  const [rowMenu, setRowMenu] = useState<{ night: number; anchor: HTMLElement } | null>(null)
  if (!trip || !tripLegs) {
    return {
      candidates: [] as CandidateMarker[],
      pickCandidate: (_arg: { hutIndex?: number; startId?: number }): void => {},
      activeLabel: null as string | null,
      renderRowMenu: (_night: number): ReactNode => null,
      renderEndpointMenu: (_which: 'start' | 'exit'): ReactNode => null,
      renderExtendButtons: (): ReactNode => null,
    }
  }
  const name = (h: number) => hutNameById.get(h) ?? String(h)
  const resolvable = tripLegs.hutIndices.every((i) => i !== null)
  const car = modeOfTrip(trip) === 'car'

  let candidates: CandidateMarker[] = []
  let pickCandidate = (_arg: { hutIndex?: number; startId?: number }): void => {}

  if (editing?.kind === 'swap') {
    candidates = swapCandidates(graph, trip, editing.index).map((c) => ({ hutIndex: c.hutIndex, legInH: c.legInH, legOutH: c.legOutH }))
    pickCandidate = ({ hutIndex }) => {
      if (hutIndex === undefined) return
      onChange(applySwap(graph, trip, editing.index, hutIndex))
      onEditing(null)
    }
  } else if (editing?.kind === 'extend') {
    candidates = extendCandidates(graph, trip, editing.side).map((c) => ({ hutIndex: c.hutIndex, legH: c.legH }))
    pickCandidate = ({ hutIndex }) => {
      if (hutIndex === undefined) return
      const next = applyExtend(graph, trip, editing.side, hutIndex)
      if (next) onChange(next)
      onEditing(null)
    }
  } else if (editing?.kind === 'start' || editing?.kind === 'exit') {
    const which = editing.kind
    const list: EndpointCandidate[] = resolvable ? endpointCandidates(graph, trip, which) : []
    candidates = list.map((c) => ({ startId: c.startId, sourceType: c.sourceType, legH: c.durationH }))
    pickCandidate = ({ startId }) => {
      const c = list.find((x) => x.startId === startId)
      if (c) onChange(applyEndpoint(trip, which, c))
      onEditing(null)
    }
  }

  const activeLabel = editing
    ? (editing.kind === 'swap' ? ACTIVE_LABEL.swap(editing.index) : ACTIVE_LABEL[editing.kind]())
    : null

  const renderRowMenu = (night: number): ReactNode => {
    if (!resolvable) return null
    const trim = trimAllowed(graph, trip, night)
    return (
      <Box sx={{ mt: 0.5 }}>
        <IconButton size="small" aria-label={`Weitere Aktionen Etappe ${night + 1}`} onClick={(e: MouseEvent<HTMLElement>) => setRowMenu({ night, anchor: e.currentTarget })}>
          <Typography component="span" sx={{ fontWeight: 700 }}>⋮</Typography>
        </IconButton>
        <Menu open={rowMenu?.night === night} anchorEl={rowMenu?.anchor ?? null} onClose={() => setRowMenu(null)}>
          <MenuItem onClick={() => { onEditing({ kind: 'swap', index: night }); setRowMenu(null) }}>Hütte tauschen</MenuItem>
          <MenuItem disabled={!trim.ok} onClick={() => { const next = applyTrim(graph, trip, night); if (next) onChange(next); setRowMenu(null) }}>
            Hütte entfernen{!trim.ok ? ` (${trim.reason})` : ''}
          </MenuItem>
        </Menu>
        {editing?.kind === 'swap' && editing.index === night && (
          <Box sx={styles.swapCandidates}>
            {candidates.length === 0 && <Typography variant="body2">Keine passende Hütte im Wegenetz.</Typography>}
            {candidates.map((c) => (
              <Button
                key={c.hutIndex} size="small" variant="outlined" color="secondary"
                sx={styles.candidateButton}
                onClick={() => pickCandidate({ hutIndex: c.hutIndex })}
              >
                <span>{name(c.hutIndex!)}</span>
                <span>{c.legInH !== undefined && `${formatSignpostTime(c.legInH)} · ${formatSignpostTime(c.legOutH ?? 0)}`}</span>
              </Button>
            ))}
            <Button size="small" onClick={() => onEditing(null)}>Abbrechen</Button>
          </Box>
        )}
      </Box>
    )
  }

  const renderEndpointMenu = (which: 'start' | 'exit'): ReactNode => {
    if (which === 'exit' && car) return null
    const current = which === 'start' ? trip.start.startId : trip.exit.startId
    return (
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <Typography variant="body2">
          {which === 'start' ? 'Start' : 'Ende'}: {car && which === 'exit' ? 'wie Start' : startLabel(current)}
        </Typography>
        <Button size="small" color="secondary" disabled={!resolvable} onClick={() => onEditing({ kind: which })}>
          {which === 'start' ? 'Anderen Start wählen' : 'Anderes Ziel wählen'}
        </Button>
        {editing?.kind === which && (
          <Box sx={styles.endpointCandidates}>
            {candidates.length === 0 && <Typography variant="body2">Keine Alternative im Wegenetz.</Typography>}
            {candidates.map((c) => (
              <Button
                key={c.startId} size="small" variant="outlined" color="secondary"
                sx={styles.candidateButton}
                onClick={() => pickCandidate({ startId: c.startId })}
              >
                <span>{startLabel(c.startId!)}</span>
                <span>{c.legH !== undefined && formatSignpostTime(c.legH)}</span>
              </Button>
            ))}
            <Button size="small" onClick={() => onEditing(null)}>Abbrechen</Button>
          </Box>
        )}
      </Box>
    )
  }

  const renderExtendButtons = (): ReactNode => {
    if (!resolvable) return null
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button size="small" color="secondary" onClick={() => onEditing({ kind: 'extend', side: 'first' })}>Etappe voranstellen</Button>
          <Button size="small" color="secondary" onClick={() => onEditing({ kind: 'extend', side: 'last' })}>Etappe anhängen</Button>
        </Box>
        {editing?.kind === 'extend' && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            {candidates.length === 0 && <Typography variant="body2">Keine passende Hütte im Wegenetz.</Typography>}
            {candidates.map((c) => (
              <Button
                key={c.hutIndex} size="small" variant="outlined" color="secondary"
                sx={styles.candidateButton}
                onClick={() => pickCandidate({ hutIndex: c.hutIndex })}
              >
                <span>{name(c.hutIndex!)}</span>
                <span>{c.legH !== undefined && formatSignpostTime(c.legH)}</span>
              </Button>
            ))}
            <Button size="small" onClick={() => onEditing(null)}>Abbrechen</Button>
          </Box>
        )}
      </Box>
    )
  }

  return { candidates, pickCandidate, renderRowMenu, renderEndpointMenu, renderExtendButtons, activeLabel }
}
