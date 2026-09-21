import { Box, Button, Typography } from '@mui/material'
import type { ReactNode } from 'react'
import { formatSignpostTime } from '../format/signpostTime.js'
import {
  applyEndpoint, applyExtend, applySwap, applyTrim, endpointCandidates, extendCandidates,
  modeOfTrip, swapCandidates, trimAllowed,
} from '../tourSearch/tripEdit.js'
import type { TripGraph, TripLegs } from '../tourSearch/tripLegs.js'
import type { Trip } from '../trip/trip.js'

export type EditingState = { kind: 'swap'; index: number } | { kind: 'extend'; side: 'first' | 'last' } | null

export interface CandidateMarker {
  hutIndex: number
  legInH?: number
  legOutH?: number
  legH?: number
}

export interface TripEditorProps {
  graph: TripGraph
  trip: Trip
  tripLegs: TripLegs
  hutNameById: Map<number, string>
  startLabel: (startId: number) => string
  editing: EditingState
  onEditing: (editing: EditingState) => void
  onChange: (trip: Trip) => void
}

/** All trip edits are moves inside the routing graph (tourSearch/tripEdit.ts); this only renders
 *  them and forwards the chosen move. Candidates also render as buttons so the edit works without
 *  the map. */
export function useTripEditor({ graph, trip, tripLegs, hutNameById, startLabel, editing, onEditing, onChange }: TripEditorProps) {
  const name = (h: number) => hutNameById.get(h) ?? String(h)
  const resolvable = tripLegs.hutIndices.every((i) => i !== null)

  let candidates: CandidateMarker[] = []
  let pickCandidate = (_hutIndex: number): void => {}
  if (editing?.kind === 'swap') {
    candidates = swapCandidates(graph, trip, editing.index)
    pickCandidate = (hutIndex) => { onChange(applySwap(graph, trip, editing.index, hutIndex)); onEditing(null) }
  } else if (editing?.kind === 'extend') {
    candidates = extendCandidates(graph, trip, editing.side).map((c) => ({ hutIndex: c.hutIndex, legH: c.legH }))
    pickCandidate = (hutIndex) => {
      const next = applyExtend(graph, trip, editing.side, hutIndex)
      if (next) onChange(next)
      onEditing(null)
    }
  }

  const renderStageControls = (night: number): ReactNode => {
    if (!resolvable) return null
    const trim = trimAllowed(graph, trip, night)
    return (
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap', mt: 0.5 }}>
        <Button size="small" color="secondary" onClick={() => onEditing({ kind: 'swap', index: night })}>Hütte tauschen</Button>
        <Button
          size="small" color="secondary" disabled={!trim.ok}
          onClick={() => { const next = applyTrim(graph, trip, night); if (next) onChange(next) }}
        >
          Hütte entfernen
        </Button>
        {!trim.ok && <Typography variant="caption" color="text.secondary">{trim.reason}</Typography>}
      </Box>
    )
  }

  const startOptions = resolvable ? endpointCandidates(graph, trip, 'start') : []
  const exitOptions = resolvable ? endpointCandidates(graph, trip, 'exit') : []
  const car = modeOfTrip(trip) === 'car'

  const extra = (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
        <Typography variant="body2">Start: {startLabel(trip.start.startId)}</Typography>
        {startOptions.map((c) => (
          <Button key={c.startId} size="small" variant="outlined" color="secondary" onClick={() => onChange(applyEndpoint(trip, 'start', c))}>
            {`Start: ${startLabel(c.startId)} wählen`}
          </Button>
        ))}
      </Box>
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
        <Typography variant="body2">Ende: {car ? 'wie Start' : startLabel(trip.exit.startId)}</Typography>
        {exitOptions.map((c) => (
          <Button key={c.startId} size="small" variant="outlined" color="secondary" onClick={() => onChange(applyEndpoint(trip, 'exit', c))}>
            {`Ende: ${startLabel(c.startId)} wählen`}
          </Button>
        ))}
      </Box>
      {resolvable && (
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button size="small" color="secondary" onClick={() => onEditing({ kind: 'extend', side: 'first' })}>Etappe voranstellen</Button>
          <Button size="small" color="secondary" onClick={() => onEditing({ kind: 'extend', side: 'last' })}>Etappe anhängen</Button>
        </Box>
      )}
      {editing && (
        <Box sx={{ borderTop: '1px solid', borderColor: 'divider', pt: 1, display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography variant="subtitle2">
            {editing.kind === 'swap' ? `Etappe ${editing.index + 1}: Hütte wählen` : 'Nächste Hütte wählen'}
          </Typography>
          {candidates.length === 0 && <Typography variant="body2">Keine passende Hütte im Wegenetz.</Typography>}
          {candidates.map((c) => (
            <Button key={c.hutIndex} size="small" variant="outlined" color="secondary" sx={{ justifyContent: 'space-between', textTransform: 'none' }} onClick={() => pickCandidate(c.hutIndex)}>
              <span>{name(c.hutIndex)}</span>
              <span>
                {c.legInH !== undefined && `${formatSignpostTime(c.legInH)} · ${formatSignpostTime(c.legOutH ?? 0)}`}
                {c.legH !== undefined && formatSignpostTime(c.legH)}
              </span>
            </Button>
          ))}
          <Button size="small" onClick={() => onEditing(null)}>Abbrechen</Button>
        </Box>
      )}
    </Box>
  )

  return { renderStageControls, extra, candidates, pickCandidate }
}
