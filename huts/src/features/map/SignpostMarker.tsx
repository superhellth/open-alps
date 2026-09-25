import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import { Marker, useMap, useMapEvents } from 'react-leaflet'
import type { MarkerKind } from './clusterStarts.js'

export const OPEN_DELAY_MS = 200
export const CLOSE_DELAY_MS = 250
/** Lifts a spread marker above every neighbour so the column is never covered. */
const SPREAD_Z_OFFSET = 10_000

export type Activation = { kind: 'tour'; tourKey: string } | { kind: 'overflow' } | { kind: 'body' }

function resolveTarget(target: EventTarget | null): Activation {
  const el = target instanceof Element ? target : null
  const board = el?.closest<HTMLElement>('[data-tour-key]')
  if (board) return { kind: 'tour', tourKey: board.dataset.tourKey! }
  if (el?.closest('[data-overflow]')) return { kind: 'overflow' }
  return { kind: 'body' }
}

const tourKeyOf = (target: EventTarget | null): string | null => {
  const a = resolveTarget(target)
  return a.kind === 'tour' ? a.tourKey : null
}

/** One signpost marker. The icon depends only on `kind` and `html`; dimmed, highlighted, spread and the
 *  spread side are classes toggled on the live icon element, so hovering never replaces the DOM under the
 *  pointer. Only a `stack` spreads. */
export default function SignpostMarker({ position, kind, html, dimmed, highlighted, onHoverMarker, onHoverTour, onActivate }: {
  position: [number, number]
  kind: MarkerKind
  html: string
  dimmed: boolean
  highlighted: boolean
  /** The pointer or focus entered (true) or left (false) the marker as a whole, spread boards included. */
  onHoverMarker: (hovering: boolean) => void
  /** The tour board under the pointer or focus; null when none. */
  onHoverTour: (key: string | null) => void
  onActivate: (a: Activation) => void
}) {
  const map = useMap()
  const markerRef = useRef<L.Marker>(null)
  const icon = useMemo(() => L.divIcon({ className: `signpost-marker ${kind}`, html, iconSize: [0, 0] }), [kind, html])
  const [spread, setSpread] = useState(false)
  const spreadRef = useRef(false)
  const timer = useRef<number | undefined>(undefined)
  const escaped = useRef(false)
  const callbacks = useRef({ onHoverMarker, onHoverTour, onActivate })
  useEffect(() => {
    spreadRef.current = spread
    callbacks.current = { onHoverMarker, onHoverTour, onActivate }
  })
  const canSpread = kind === 'stack'

  const cancelTimer = () => window.clearTimeout(timer.current)
  const later = (fn: () => void, ms: number) => { cancelTimer(); timer.current = window.setTimeout(fn, ms) }
  const collapse = () => { cancelTimer(); setSpread(false) }
  useMapEvents({ zoomstart: collapse, dragstart: collapse })
  useEffect(() => cancelTimer, [])

  useEffect(() => {
    const el = markerRef.current?.getElement()
    if (!el) return
    el.classList.toggle('dimmed', dimmed)
    el.classList.toggle('highlighted', highlighted)
  }, [icon, dimmed, highlighted])

  useEffect(() => {
    const marker = markerRef.current
    const el = marker?.getElement()
    if (!marker || !el) return
    el.classList.toggle('spread', spread)
    marker.setZIndexOffset(spread ? SPREAD_Z_OFFSET : 0)
    if (spread) {
      const toLeft = map.latLngToContainerPoint(marker.getLatLng()).x > map.getSize().x / 2
      el.classList.toggle('to-left', toLeft)
      el.classList.toggle('to-right', !toLeft)
    }
  }, [icon, spread, map])

  useEffect(() => {
    const el = markerRef.current?.getElement()
    if (!el) return
    const inside = (t: EventTarget | null) => t instanceof Node && el.contains(t)
    const onOver = (e: MouseEvent) => {
      escaped.current = false
      cancelTimer()
      callbacks.current.onHoverMarker(true)
      callbacks.current.onHoverTour(tourKeyOf(e.target))
      if (canSpread && !spreadRef.current) later(() => setSpread(true), OPEN_DELAY_MS)
    }
    const onOut = (e: MouseEvent) => {
      if (inside(e.relatedTarget)) return
      callbacks.current.onHoverMarker(false)
      callbacks.current.onHoverTour(null)
      later(() => setSpread(false), CLOSE_DELAY_MS)
    }
    const onFocusIn = (e: FocusEvent) => {
      cancelTimer()
      callbacks.current.onHoverMarker(true)
      callbacks.current.onHoverTour(tourKeyOf(e.target))
      if (canSpread && !escaped.current) setSpread(true)
    }
    const onFocusOut = (e: FocusEvent) => {
      if (inside(e.relatedTarget)) return
      escaped.current = false
      callbacks.current.onHoverMarker(false)
      callbacks.current.onHoverTour(null)
      setSpread(false)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault()
        callbacks.current.onActivate(resolveTarget(e.target))
      } else if (e.key === 'Escape' && spreadRef.current) {
        escaped.current = true
        el.querySelector<HTMLElement>('.sign')?.focus()
        setSpread(false)
      }
    }
    el.addEventListener('mouseover', onOver)
    el.addEventListener('mouseout', onOut)
    el.addEventListener('focusin', onFocusIn)
    el.addEventListener('focusout', onFocusOut)
    el.addEventListener('keydown', onKeyDown)
    return () => {
      el.removeEventListener('mouseover', onOver)
      el.removeEventListener('mouseout', onOut)
      el.removeEventListener('focusin', onFocusIn)
      el.removeEventListener('focusout', onFocusOut)
      el.removeEventListener('keydown', onKeyDown)
    }
  }, [icon, canSpread])

  return (
    <Marker
      ref={markerRef} position={position} icon={icon} keyboard={false}
      eventHandlers={{ click: (e) => callbacks.current.onActivate(resolveTarget(e.originalEvent.target)) }}
    />
  )
}
