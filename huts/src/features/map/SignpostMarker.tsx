import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import { Marker } from 'react-leaflet'
import { HOVER_Z_OFFSET } from './routePanes.js'

/** Lifts a previewing dot above every neighbour, hovered ones included, so its board is never covered. */
const PREVIEW_Z_OFFSET = 10_000

export type SignpostKind = 'board' | 'dot'

const TOUR_ELEMENT = '[data-tour-key]'

/** One signpost marker: a board on a mast, or a foot dot whose board shows as a preview while its tour is hovered or
 *  focused, or highlighted from elsewhere. The icon depends only on `kind` and `html`; dimmed, highlighted and previewing
 *  are classes toggled on the live icon element, so hovering never replaces the DOM under the pointer. */
export default function SignpostMarker({ position, kind, html, dimmed, highlighted, fadedKeys, onHoverMarker, onActivate }: {
  position: [number, number]
  kind: SignpostKind
  html: string
  dimmed: boolean
  highlighted: boolean
  /** Tour keys whose boards are drawn faded. */
  fadedKeys: ReadonlySet<string>
  /** The pointer or focus entered (true) or left (false) the marker. */
  onHoverMarker: (hovering: boolean) => void
  /** The board or dot was clicked or Enter was pressed on it. */
  onActivate: () => void
}) {
  const markerRef = useRef<L.Marker>(null)
  const icon = useMemo(() => L.divIcon({ className: `signpost-marker ${kind}`, html, iconSize: [0, 0] }), [kind, html])
  const [engaged, setEngaged] = useState(false)
  const previewing = kind === 'dot' && (engaged || highlighted)
  const callbacks = useRef({ onHoverMarker, onActivate })
  useEffect(() => { callbacks.current = { onHoverMarker, onActivate } })

  // A replaced icon element never fires `mouseout`, so the engaged state ends with it.
  useEffect(() => { setEngaged(false) }, [icon])

  useEffect(() => {
    const el = markerRef.current?.getElement()
    if (!el) return
    el.classList.toggle('dimmed', dimmed)
    el.classList.toggle('highlighted', highlighted)
    el.classList.toggle('previewing', previewing)
  }, [icon, dimmed, highlighted, previewing])

  useEffect(() => {
    markerRef.current?.setZIndexOffset(previewing ? PREVIEW_Z_OFFSET : highlighted ? HOVER_Z_OFFSET : 0)
  }, [icon, previewing, highlighted])

  useEffect(() => {
    markerRef.current?.getElement()?.querySelectorAll<HTMLElement>(`.sign${TOUR_ELEMENT}`)
      .forEach((board) => board.classList.toggle('faded', fadedKeys.has(board.dataset.tourKey!)))
  }, [icon, fadedKeys])

  useEffect(() => {
    const el = markerRef.current?.getElement()
    if (!el) return
    const inside = (t: EventTarget | null) => t instanceof Node && el.contains(t)
    const enter = () => { setEngaged(true); callbacks.current.onHoverMarker(true) }
    const leave = (e: MouseEvent | FocusEvent) => {
      if (inside(e.relatedTarget)) return
      setEngaged(false)
      callbacks.current.onHoverMarker(false)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Enter' || !(e.target instanceof Element) || !e.target.closest(TOUR_ELEMENT)) return
      e.preventDefault()
      callbacks.current.onActivate()
    }
    el.addEventListener('mouseover', enter)
    el.addEventListener('mouseout', leave)
    el.addEventListener('focusin', enter)
    el.addEventListener('focusout', leave)
    el.addEventListener('keydown', onKeyDown)
    return () => {
      el.removeEventListener('mouseover', enter)
      el.removeEventListener('mouseout', leave)
      el.removeEventListener('focusin', enter)
      el.removeEventListener('focusout', leave)
      el.removeEventListener('keydown', onKeyDown)
    }
  }, [icon])

  return (
    <Marker
      ref={markerRef} position={position} icon={icon} keyboard={false}
      eventHandlers={{
        click: (e) => {
          const target = e.originalEvent.target
          if (target instanceof Element && target.closest(TOUR_ELEMENT)) callbacks.current.onActivate()
        },
      }}
    />
  )
}
