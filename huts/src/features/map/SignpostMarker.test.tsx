// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { render, cleanup, fireEvent, act } from '@testing-library/react'
import L from 'leaflet'
import { MapContainer, useMap } from 'react-leaflet'
import SignpostMarker, { CLOSE_DELAY_MS, OPEN_DELAY_MS } from './SignpostMarker.js'
import { stackHtml, singleHtml } from './signpostHtml.js'
import type { BoardTour } from './signpostHtml.js'

const bt = (i: number): BoardTour => ({ key: `k${i}`, label: { text: `Z${i}`, distance: '1.0 km', title: `t${i}` } })
let map: L.Map
function CaptureMap() { map = useMap(); return null }

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { cleanup(); vi.useRealTimers() })

function setup(over: Partial<Parameters<typeof SignpostMarker>[0]> = {}) {
  const handlers = { onHoverMarker: vi.fn(), onHoverTour: vi.fn(), onActivate: vi.fn() }
  const utils = render(
    <MapContainer center={[47, 11]} zoom={13} style={{ height: 400, width: 400 }}>
      <CaptureMap />
      <SignpostMarker position={[47, 11]} kind="stack" html={stackHtml([bt(1), bt(2)])} dimmed={false} highlighted={false} fadedKeys={new Set()} {...handlers} {...over} />
    </MapContainer>,
  )
  const el = () => utils.container.querySelector('.signpost-marker') as HTMLElement
  return { ...utils, ...handlers, el }
}
const advance = (ms: number) => act(() => { vi.advanceTimersByTime(ms) })

describe('SignpostMarker spread', () => {
  it('does not spread before the open delay and spreads after it', () => {
    const { el } = setup()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS - 1)
    expect(el().classList.contains('spread')).toBe(false)
    advance(1)
    expect(el().classList.contains('spread')).toBe(true)
  })
  it('does not collapse inside the close delay, collapses after it', () => {
    const { el } = setup()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS)
    fireEvent.mouseOut(el().querySelector('.sign')!, { relatedTarget: document.body })
    advance(CLOSE_DELAY_MS - 1)
    expect(el().classList.contains('spread')).toBe(true)
    advance(1)
    expect(el().classList.contains('spread')).toBe(false)
  })
  it('stays open when the pointer crosses from one board to another', () => {
    const { el } = setup()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS)
    const [a, b] = el().querySelectorAll('.board')
    fireEvent.mouseOut(a, { relatedTarget: b })
    fireEvent.mouseOver(b)
    advance(CLOSE_DELAY_MS * 2)
    expect(el().classList.contains('spread')).toBe(true)
  })
  it('collapses at once on zoomstart and on dragstart', () => {
    const { el } = setup()
    for (const event of ['zoomstart', 'dragstart']) {
      fireEvent.mouseOver(el().querySelector('.sign')!)
      advance(OPEN_DELAY_MS)
      expect(el().classList.contains('spread')).toBe(true)
      act(() => { map.fire(event) })
      expect(el().classList.contains('spread')).toBe(false)
    }
  })
  it('raises a spread marker above its neighbours', () => {
    const { el } = setup()
    const before = Number(el().style.zIndex)
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS)
    expect(Number(el().style.zIndex)).toBeGreaterThan(before + 5000)
  })
  it('does not spread a single or a cluster marker', () => {
    const { el } = setup({ kind: 'single', html: singleHtml(bt(1)) })
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS * 2)
    expect(el().classList.contains('spread')).toBe(false)
  })
  it('keeps its spread state when the html changes while spread', () => {
    const { el, rerender } = setup()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS)
    rerender(
      <MapContainer center={[47, 11]} zoom={13} style={{ height: 400, width: 400 }}>
        <CaptureMap />
        <SignpostMarker position={[47, 11]} kind="stack" html={stackHtml([bt(1), bt(2), bt(3)])} dimmed={false} highlighted={false} fadedKeys={new Set()} onHoverMarker={() => {}} onHoverTour={() => {}} onActivate={() => {}} />
      </MapContainer>,
    )
    expect(el().classList.contains('spread')).toBe(true)
  })
  it('does not fire a pending timer after unmount', () => {
    const { el, unmount } = setup()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    unmount()
    expect(() => advance(OPEN_DELAY_MS * 2)).not.toThrow()
  })
})

describe('SignpostMarker events', () => {
  it('reports the hovered board and clears it on leaving', () => {
    const { el, onHoverTour, onHoverMarker } = setup()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS)
    fireEvent.mouseOver(el().querySelector('.board[data-tour-key="k2"]')!)
    expect(onHoverTour).toHaveBeenLastCalledWith('k2')
    fireEvent.mouseOut(el().querySelector('.board[data-tour-key="k2"]')!, { relatedTarget: document.body })
    expect(onHoverTour).toHaveBeenLastCalledWith(null)
    expect(onHoverMarker).toHaveBeenLastCalledWith(false)
  })
  it('activates a board, the overflow board and the body sign from clicks', () => {
    const many = Array.from({ length: 10 }, (_, i) => bt(i))
    const { el, onActivate } = setup({ html: stackHtml(many) })
    fireEvent.click(el().querySelector('.board[data-tour-key="k3"]')!)
    expect(onActivate).toHaveBeenLastCalledWith({ kind: 'tour', tourKey: 'k3' })
    fireEvent.click(el().querySelector('[data-overflow]')!)
    expect(onActivate).toHaveBeenLastCalledWith({ kind: 'overflow' })
    fireEvent.click(el().querySelector('.stack-sign')!)
    expect(onActivate).toHaveBeenLastCalledWith({ kind: 'body' })
  })
  it('toggles dimmed and highlighted as classes', () => {
    const { el } = setup({ dimmed: true, highlighted: true })
    expect(el().classList.contains('dimmed')).toBe(true)
    expect(el().classList.contains('highlighted')).toBe(true)
  })
})

describe('SignpostMarker keyboard', () => {
  it('spreads on focus at once, activates a board with Enter, collapses with Escape', () => {
    const { el, onActivate } = setup()
    fireEvent.focusIn(el().querySelector('.sign')!)
    expect(el().classList.contains('spread')).toBe(true)
    fireEvent.keyDown(el().querySelector('.board[data-tour-key="k1"]')!, { key: 'Enter' })
    expect(onActivate).toHaveBeenLastCalledWith({ kind: 'tour', tourKey: 'k1' })
    fireEvent.keyDown(el().querySelector('.board[data-tour-key="k1"]')!, { key: 'Escape' })
    expect(el().classList.contains('spread')).toBe(false)
  })
  it('focusing a board highlights its tour', () => {
    const { el, onHoverTour } = setup()
    fireEvent.focusIn(el().querySelector('.board[data-tour-key="k2"]')!)
    expect(onHoverTour).toHaveBeenLastCalledWith('k2')
  })
})

describe('SignpostMarker board placement', () => {
  const at = (x: number) => {
    vi.spyOn(L.Map.prototype, 'getSize').mockImplementation(() => L.point(1000, 600))
    vi.spyOn(L.Map.prototype, 'latLngToContainerPoint').mockImplementation(() => L.point(x, 300))
  }
  const single = (heading: 'east' | 'west') => setup({ kind: 'single', html: singleHtml(bt(1), heading), heading })

  it('puts a single board on its heading side of the mast', () => {
    at(500)
    expect(single('east').el().classList.contains('side-right')).toBe(true)
    cleanup()
    expect(single('west').el().classList.contains('side-left')).toBe(true)
  })
  it('flips a board that would leave the viewport, keeping the arrow direction', () => {
    at(950)
    const { el, container } = single('east')
    expect(el().classList.contains('side-left')).toBe(true)
    expect(container.querySelector('.sign')!.classList.contains('heads-west')).toBe(false)
  })
  it('fades boards of the given tour keys and leaves the others opaque', () => {
    const { container } = setup({ fadedKeys: new Set(['k1']) })
    expect(container.querySelector('[data-tour-key="k1"]')!.classList.contains('faded')).toBe(true)
    expect(container.querySelector('[data-tour-key="k2"]')!.classList.contains('faded')).toBe(false)
  })
})
