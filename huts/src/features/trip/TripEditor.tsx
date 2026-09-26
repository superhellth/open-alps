import { applyEndpoint, applyExtend, applySwap, applyTrim, endpointCandidates, extendCandidates, modeOfTrip, swapCandidates, trimAllowed } from '@/trip/tripEdit.js'
import type { EndpointCandidate, TrimCheck } from '@/trip/tripEdit.js'
import type { TripLegs } from '@/trip/tripLegs.js'
import type { SourceType, TripGraph } from '@/tourSearch/types.js'
import type { Trip } from '@/trip/trip.js'

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
  editing: EditingState
  onEditing: (editing: EditingState) => void
  onChange: (trip: Trip) => void
}

/** What the editor offers the trip panel: the current candidates and the moves that start, apply or cancel an edit. */
export interface TripEditor {
  editing: EditingState
  /** false while a night no longer resolves; swaps, trims and extends are then unavailable. */
  editable: boolean
  /** Car trips exit where they started; the exit cannot be changed. */
  car: boolean
  candidates: CandidateMarker[]
  pickCandidate: (arg: { hutIndex?: number; startId?: number }) => void
  activeLabel: string | null
  trimAllowed: (night: number) => TrimCheck
  trim: (night: number) => void
  startSwap: (night: number) => void
  startExtend: (side: 'first' | 'last') => void
  startEndpoint: (which: 'start' | 'exit') => void
  cancel: () => void
}

const ACTIVE_LABEL = {
  swap: (index: number) => `Neue Hütte für Etappe ${index + 1} wählen`,
  extend: () => 'Nächste Hütte wählen',
  start: () => 'Neuen Start wählen',
  exit: () => 'Neues Ziel wählen',
}

const noop = () => {}

/** All trip edits are moves inside the routing graph (trip/tripEdit.ts); this exposes the current
 *  candidates and the actions the rows trigger. Candidates render both as map markers (the caller
 *  places them via `candidates`/`pickCandidate`) and as buttons under the row (`CandidateList`),
 *  so every edit works without the map. */
export function useTripEditor({ graph, trip, tripLegs, editing, onEditing, onChange }: TripEditorProps): TripEditor {
  const cancel = () => onEditing(null)
  if (!trip || !tripLegs) {
    return {
      editing, editable: false, car: false, candidates: [], pickCandidate: noop, activeLabel: null,
      trimAllowed: () => ({ ok: false, reason: '' }), trim: noop, startSwap: noop, startExtend: noop, startEndpoint: noop, cancel,
    }
  }
  const editable = tripLegs.hutIndices.every((i) => i !== null)

  let candidates: CandidateMarker[] = []
  let pickCandidate: TripEditor['pickCandidate'] = noop

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
    const list: EndpointCandidate[] = editable ? endpointCandidates(graph, trip, which) : []
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

  return {
    editing, editable, car: modeOfTrip(trip) === 'car', candidates, pickCandidate, activeLabel,
    trimAllowed: (night) => trimAllowed(graph, trip, night),
    trim: (night) => {
      const next = applyTrim(graph, trip, night)
      if (next) onChange(next)
    },
    startSwap: (night) => onEditing({ kind: 'swap', index: night }),
    startExtend: (side) => onEditing({ kind: 'extend', side }),
    startEndpoint: (which) => onEditing({ kind: which }),
    cancel,
  }
}
