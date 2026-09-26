import { useCallback, useEffect, useMemo, useState } from 'react'
import type { AppData } from '@/data/buildAppData.js'
import type { SearchClient } from '@/search/searchClient.js'
import { legsFromTrip } from '@/trip/tripLegs.js'
import type { ProfilePosition } from '@/trip/tripLegs.js'
import { shareUrl } from '@/trip/shareLink.js'
import type { Trip } from '@/trip/trip.js'
import { useTrips } from '@/trip/tripsContext.js'
import { useTripEditor } from './TripEditor.js'
import type { EditingState } from './TripEditor.js'
import { useTripOverlaps } from './useTripOverlaps.js'

/** The open trip: its derived legs, editor, share link, and the draft-discard confirmation. */
export function useTripSession({ data, client, startLabel }: { data: AppData; client: SearchClient; startLabel: (startId: number) => string }) {
  const { dispatch, activeTrip, isDraft, draftDirty } = useTrips()
  const [editing, setEditing] = useState<EditingState>(null)
  const [highlightedLeg, setHighlightedLeg] = useState<number | null>(null)
  const [profileCursor, setProfileCursor] = useState<ProfilePosition | null>(null)
  const [editMode, setEditModeState] = useState(false)
  /** Turning edit mode off also cancels a pending edit. */
  const setEditMode = useCallback((on: boolean) => {
    setEditModeState(on)
    if (!on) setEditing(null)
  }, [])
  const [shareNote, setShareNote] = useState<string | null>(null)
  const [shareFallback, setShareFallback] = useState<string | null>(null)
  const [pendingPick, setPendingPick] = useState<Trip | null>(null)
  const [openedFrom, setOpenedFrom] = useState<'results' | 'saved'>('results')

  const tripLegs = useMemo(() => (activeTrip ? legsFromTrip(data.graph, activeTrip) : null), [activeTrip, data])
  const tripId = activeTrip?.id ?? null
  const nightCount = activeTrip?.huts.length ?? 0
  // A different trip starts in view mode; a hovered row that vanished never fires mouseleave.
  useEffect(() => { setEditModeState(false); setEditing(null) }, [tripId])
  useEffect(() => { setHighlightedLeg(null); setProfileCursor(null) }, [tripId, nightCount])
  const mode: 'trip' | 'discover' = activeTrip && tripLegs ? 'trip' : 'discover'
  const overlapWarnings = useTripOverlaps(client, activeTrip, tripLegs)

  const editor = useTripEditor({
    graph: data.graph, trip: activeTrip, tripLegs,
    editing, onEditing: setEditing,
    onChange: (trip) => dispatch({ type: isDraft ? 'updateDraft' : 'update', trip }),
  })

  /** Opens `trip` as a draft; while the current draft has unsaved edits it waits in `pendingPick` for confirmation. Returns whether it opened. */
  const openDraft = useCallback((trip: Trip): boolean => {
    if (draftDirty) { setPendingPick(trip); return false }
    setOpenedFrom('results')
    dispatch({ type: 'openDraft', trip })
    setEditing(null)
    return true
  }, [draftDirty, dispatch])

  const confirmDiscardDraft = useCallback(() => {
    if (pendingPick) {
      setOpenedFrom('results')
      dispatch({ type: 'openDraft', trip: pendingPick })
    }
    setPendingPick(null)
    setEditing(null)
  }, [pendingPick, dispatch])
  const cancelPendingPick = useCallback(() => setPendingPick(null), [])

  const share = useCallback(async () => {
    if (!activeTrip) return
    const url = shareUrl(activeTrip, window.location)
    try {
      await navigator.clipboard.writeText(url)
      setShareNote('Link kopiert')
    } catch {
      setShareFallback(url)
    }
  }, [activeTrip])

  const candidateStartCoords = useMemo(() => new Map(editor.candidates.flatMap((c) => {
    if (c.startId === undefined) return []
    const p = data.startById.get(c.startId)
    return p ? [[c.startId, { lat: p.lat, lng: p.lng }] as const] : []
  })), [data, editor.candidates])
  const candidateMarkers = useMemo(() => editor.candidates.flatMap((c) => {
    if (c.hutIndex !== undefined) {
      const p = data.hutCoordsById.get(c.hutIndex)
      return p ? [{ ...c, name: data.hutNameById.get(c.hutIndex) ?? String(c.hutIndex) }] : []
    }
    if (c.startId !== undefined) return [{ ...c, name: startLabel(c.startId) }]
    return []
  }), [data, editor.candidates, startLabel])
  const tripHuts = useMemo(() => tripLegs
    ? tripLegs.hutIndices.flatMap((i) => {
        const cls = i === null ? undefined : data.hutClassByIndex.get(i)
        return i !== null && cls ? [{ hutIndex: i, name: data.hutNameById.get(i) ?? String(i), operator: cls.operator, serviced: cls.serviced }] : []
      })
    : [], [data, tripLegs])
  const tripEnds = useMemo(() => activeTrip
    ? [activeTrip.start, activeTrip.exit].flatMap((e) => {
        const p = data.startById.get(e.startId)
        return p ? [{ lat: p.lat, lng: p.lng, sourceType: e.sourceType as number }] : []
      })
    : [], [data, activeTrip])
  const tripStopNames = useMemo(() => activeTrip && tripLegs
    ? [
        startLabel(activeTrip.start.startId),
        ...tripLegs.hutIndices.map((i) => (i === null ? 'Unbekannte Hütte' : data.hutNameById.get(i) ?? String(i))),
        startLabel(activeTrip.exit.startId),
      ]
    : [], [data, activeTrip, tripLegs, startLabel])

  return {
    activeTrip, isDraft, tripLegs, mode, overlapWarnings,
    editing, setEditing, editMode, setEditMode, editor, highlightedLeg, setHighlightedLeg, profileCursor, setProfileCursor,
    shareNote, setShareNote, shareFallback, share,
    pendingPick, openDraft, confirmDiscardDraft, cancelPendingPick,
    openedFrom, setOpenedFrom,
    candidateMarkers, candidateStartCoords, tripHuts, tripEnds, tripStopNames,
  }
}
