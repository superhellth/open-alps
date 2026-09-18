import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Box, Button, Stack, Typography } from '@mui/material'
import * as api from './api.js'
import { densify } from './densify.js'
import EditorMap from './EditorMap.js'
import {
  deleteEdit, insertEdit, listPoints, moveEdit, parseGpx, serializeGpx, type GpxDoc,
} from './gpxDoc.js'
import { History, composite, type Edit } from './history.js'
import {
  endpointRequiresHut, legShape, legStatus, tourDiscontinuous, type LegShape, type LegStatus,
} from './legStatus.js'
import Sidebar, { type SidebarTour } from './Sidebar.js'
import { SnapContext } from './snap.js'
import type { Hub } from './types.js'

interface Session {
  tour: string
  leg: number
  gpx: GpxDoc
  history: History
  mtime: string
}

const key = (tour: string, leg: number) => `${tour}/${leg}`
const LOAD_CONCURRENCY = 6

export default function EditorApp() {
  const [tours, setTours] = useState<api.TourListing[]>([])
  const [hubs, setHubs] = useState<Hub[]>([])
  const [maxSnapM, setMaxSnapM] = useState<number | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [shapes, setShapes] = useState<Record<string, LegShape>>({})
  const [session, setSession] = useState<Session | null>(null)
  const [tick, setTick] = useState(0)
  const bump = () => setTick((t) => t + 1)

  const snapCtx = useMemo(() => (hubs.length > 0 ? new SnapContext(hubs) : null), [hubs])
  const snapEnabled = snapCtx !== null && maxSnapM !== null

  // Initial load: tours, hubs, config, then every leg's endpoints (for sidebar badges).
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const list = await api.getTours()
        if (cancelled) return
        setTours(list)
        const [hubsResult, cfgResult] = await Promise.allSettled([api.getHubs(), api.getConfig()])
        if (cancelled) return
        if (hubsResult.status === 'fulfilled') setHubs(hubsResult.value)
        if (cfgResult.status === 'fulfilled') setMaxSnapM(cfgResult.value.maxSnapM)
        const failed = [hubsResult, cfgResult].filter((r) => r.status === 'rejected') as PromiseRejectedResult[]
        if (failed.length > 0) {
          setWarning(`Snap overlay disabled: ${failed.map((f) => (f.reason as Error).message).join('; ')}`)
        }
        const queue = list.flatMap((t) => t.legs.map((leg) => ({ tour: t.name, leg })))
        const worker = async () => {
          for (let item = queue.shift(); item; item = queue.shift()) {
            try {
              const { text } = await api.getLeg(item.tour, item.leg)
              const shape = legShape(listPoints(parseGpx(text)))
              if (shape && !cancelled) setShapes((s) => ({ ...s, [key(item.tour, item.leg)]: shape }))
            } catch {
              // a leg that fails to load simply shows no badge
            }
          }
        }
        await Promise.all(Array.from({ length: LOAD_CONCURRENCY }, worker))
      } catch (e) {
        setMessage((e as Error).message)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const sessionRef = useRef<Session | null>(null)
  sessionRef.current = session

  const points = useMemo(
    () => (session ? listPoints(session.gpx) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [session, tick],
  )
  const activeShape = useMemo(() => legShape(points), [points])
  const dirty = session ? session.history.isDirty() : false

  // Live statuses for every leg; the open leg uses its in-memory points.
  const statuses = useMemo(() => {
    const out: Record<string, LegStatus | null> = {}
    if (!snapCtx || maxSnapM === null) return out
    for (const t of tours) {
      t.legs.forEach((leg, position) => {
        const isActive = session?.tour === t.name && session.leg === leg
        const shape = isActive ? activeShape : shapes[key(t.name, leg)]
        out[key(t.name, leg)] = shape ? legStatus(snapCtx, shape, position, t.legs.length, maxSnapM) : null
      })
    }
    return out
  }, [tours, shapes, snapCtx, maxSnapM, session, activeShape])

  const sidebarTours: SidebarTour[] = useMemo(
    () =>
      tours.map((t) => ({
        name: t.name,
        discontinuous: tourDiscontinuous(t.legs.map((leg) => statuses[key(t.name, leg)] ?? null)),
        legs: t.legs.map((leg) => {
          const st = statuses[key(t.name, leg)]
          return {
            leg,
            snapKnown: !!st,
            startUnsnapped: !!st && !st.startOk,
            endUnsnapped: !!st && !st.endOk,
            longSegment: st ? st.longSegment : false,
            dirty: session?.tour === t.name && session.leg === leg && dirty,
          }
        }),
      })),
    [tours, statuses, session, dirty],
  )

  const openLeg = useCallback(async (tour: string, leg: number) => {
    try {
      const { text, mtime } = await api.getLeg(tour, leg)
      setSession({ tour, leg, gpx: parseGpx(text), history: new History(), mtime })
      setMessage(null)
    } catch (e) {
      setMessage((e as Error).message)
    }
  }, [])

  const onSelect = (tour: string, leg: number) => {
    if (sessionRef.current?.history.isDirty() && !window.confirm('Discard unsaved edits on the open leg?')) return
    void openLeg(tour, leg)
  }

  const run = (edit: Edit) => {
    session?.history.run(edit)
    bump()
  }
  const undo = () => {
    if (session?.history.undo()) bump()
  }
  const redo = () => {
    if (session?.history.redo()) bump()
  }

  const save = async () => {
    const s = sessionRef.current
    if (!s) return
    try {
      let res = await api.putLeg(s.tour, s.leg, serializeGpx(s.gpx), s.mtime)
      if (!res.ok) {
        const overwrite = window.confirm(
          'This GPX file changed on disk since you opened it.\nOK = overwrite it with your edits.\nCancel = reload from disk (your edits are discarded).',
        )
        if (!overwrite) return void (await openLeg(s.tour, s.leg))
        s.mtime = (await api.getLeg(s.tour, s.leg)).mtime
        res = await api.putLeg(s.tour, s.leg, serializeGpx(s.gpx), s.mtime)
        if (!res.ok) throw new Error('file changed again while saving')
      }
      s.mtime = res.mtime
      s.history.markSaved()
      setMessage(null)
      bump()
    } catch (e) {
      setMessage(`Save failed: ${(e as Error).message}`)
    }
  }

  const activeStatus = session ? statuses[key(session.tour, session.leg)] ?? null : null
  const position = session ? tours.find((t) => t.name === session.tour)?.legs.indexOf(session.leg) ?? 0 : 0
  const nLegs = session ? tours.find((t) => t.name === session.tour)?.legs.length ?? 1 : 1
  const requireHut = useMemo(() => endpointRequiresHut(position, nLegs), [position, nLegs])

  const snapEndpoint = (which: 'start' | 'end') => {
    const s = sessionRef.current
    const hub = activeStatus?.[which].nearest
    if (!s || !hub || points.length < 2) return
    const target = { lon: hub.lon, lat: hub.lat }
    const last = points.length - 1
    if (which === 'start') {
      const old = points[0]!
      run(composite([
        moveEdit(s.gpx, 0, target),
        insertEdit(s.gpx, 0, [...densify(target, old), old]),
      ]))
    } else {
      const old = points[last]!
      run(composite([
        moveEdit(s.gpx, last, target),
        insertEdit(s.gpx, last - 1, [old, ...densify(old, target)]),
      ]))
    }
  }

  // Global keys + unload guard read the latest handlers via a ref.
  const handlers = useRef({ save, undo, redo })
  handlers.current = { save, undo, redo }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return
      const k = e.key.toLowerCase()
      if (k === 's') {
        e.preventDefault()
        void handlers.current.save()
      } else if (k === 'z') {
        e.preventDefault()
        if (e.shiftKey) handlers.current.redo()
        else handlers.current.undo()
      }
    }
    const onUnload = (e: BeforeUnloadEvent) => {
      if (sessionRef.current?.history.isDirty()) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('beforeunload', onUnload)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('beforeunload', onUnload)
    }
  }, [])

  return (
    <Box sx={{ display: 'flex', height: '100vh' }}>
      <Sidebar
        tours={sidebarTours}
        active={session ? { tour: session.tour, leg: session.leg } : null}
        onSelect={onSelect}
      />
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Stack direction="row" spacing={1} sx={{ p: 1, alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography variant="subtitle2" sx={{ mr: 2 }}>
            {session ? `${session.tour} - leg ${session.leg}` : 'Select a leg'}
          </Typography>
          <Button size="small" variant="contained" disabled={!dirty} onClick={() => void save()}>Save</Button>
          <Button size="small" disabled={!session?.history.canUndo()} onClick={undo}>Undo</Button>
          <Button size="small" disabled={!session?.history.canRedo()} onClick={redo}>Redo</Button>
          {snapEnabled && activeStatus && !activeStatus.startOk && activeStatus.start.nearest && (
            <Button size="small" color="error" onClick={() => snapEndpoint('start')}>Snap start to hub</Button>
          )}
          {snapEnabled && activeStatus && !activeStatus.endOk && activeStatus.end.nearest && (
            <Button size="small" color="error" onClick={() => snapEndpoint('end')}>Snap end to hub</Button>
          )}
        </Stack>
        {warning && <Alert severity="warning" sx={{ mx: 1 }}>{warning}</Alert>}
        {message && <Alert severity="error" sx={{ mx: 1 }} onClose={() => setMessage(null)}>{message}</Alert>}
        <Box sx={{ flex: 1, minHeight: 0 }}>
          <EditorMap
            legKey={session ? key(session.tour, session.leg) : ''}
            points={points}
            hubs={hubs}
            snapCtx={snapEnabled ? snapCtx : null}
            maxSnapM={maxSnapM}
            requireHut={requireHut}
            onMove={(i, lon, lat) => session && run(moveEdit(session.gpx, i, { lon, lat }))}
            onInsert={(after, lon, lat) => session && run(insertEdit(session.gpx, after, [{ lon, lat }]))}
            onDelete={(i) => session && i > 0 && i < points.length - 1 && run(deleteEdit(session.gpx, i))}
          />
        </Box>
      </Box>
    </Box>
  )
}
