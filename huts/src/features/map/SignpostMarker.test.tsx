// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, cleanup, fireEvent } from '@testing-library/react'
import { MapContainer } from 'react-leaflet'
import SignpostMarker from './SignpostMarker.js'
import { dotHtml, singleHtml } from './signpostHtml.js'
import type { BoardTour } from './signpostHtml.js'

const bt = (i: number): BoardTour => ({ key: `k${i}`, label: { text: `Z${i}`, distance: '1.0 km', title: `t${i}` } })

afterEach(cleanup)

function setup(over: Partial<Parameters<typeof SignpostMarker>[0]> = {}) {
  const handlers = { onHoverMarker: vi.fn(), onActivate: vi.fn() }
  const tree = (props: Partial<Parameters<typeof SignpostMarker>[0]>) => (
    <MapContainer center={[47, 11]} zoom={13} style={{ height: 400, width: 400 }}>
      <SignpostMarker
        position={[47, 11]} kind="dot" html={dotHtml(bt(1), 'right')} dimmed={false} highlighted={false}
        {...handlers} {...props}
      />
    </MapContainer>
  )
  const utils = render(tree(over))
  const el = () => utils.container.querySelector('.signpost-marker') as HTMLElement
  return { ...utils, ...handlers, el, again: (props: Partial<Parameters<typeof SignpostMarker>[0]>) => utils.rerender(tree({ ...over, ...props })) }
}
const board = (over: Partial<Parameters<typeof SignpostMarker>[0]> = {}) => setup({ kind: 'board', html: singleHtml(bt(1), 'right'), ...over })

describe('SignpostMarker board', () => {
  it('has the board kind class and toggles dimmed and highlighted', () => {
    const { el } = board({ dimmed: true, highlighted: true })
    expect(el().classList.contains('board')).toBe(true)
    expect(el().classList.contains('dimmed')).toBe(true)
    expect(el().classList.contains('highlighted')).toBe(true)
  })
  it('reports hover and leave of the marker', () => {
    const { el, onHoverMarker } = board()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    expect(onHoverMarker).toHaveBeenLastCalledWith(true)
    fireEvent.mouseOut(el().querySelector('.sign')!, { relatedTarget: document.body })
    expect(onHoverMarker).toHaveBeenLastCalledWith(false)
  })
  it('reports focus and blur of the board', () => {
    const { el, onHoverMarker } = board()
    fireEvent.focusIn(el().querySelector('.sign')!)
    expect(onHoverMarker).toHaveBeenLastCalledWith(true)
    fireEvent.focusOut(el().querySelector('.sign')!, { relatedTarget: null })
    expect(onHoverMarker).toHaveBeenLastCalledWith(false)
  })
  it('activates on click and on Enter, not on a click beside the board', () => {
    const { el, onActivate } = board()
    fireEvent.click(el().querySelector('.mast')!)
    expect(onActivate).not.toHaveBeenCalled()
    fireEvent.click(el().querySelector('.sign')!)
    expect(onActivate).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(el().querySelector('.sign')!, { key: 'Enter' })
    expect(onActivate).toHaveBeenCalledTimes(2)
  })
  it('never previews, even when highlighted', () => {
    expect(board({ highlighted: true }).el().classList.contains('previewing')).toBe(false)
  })
})

describe('SignpostMarker dot', () => {
  it('has the dot kind class and no preview at rest', () => {
    const { el } = setup()
    expect(el().classList.contains('dot')).toBe(true)
    expect(el().classList.contains('previewing')).toBe(false)
  })
  it('previews on hover and hides on leave', () => {
    const { el } = setup()
    fireEvent.mouseOver(el().querySelector('.dot')!)
    expect(el().classList.contains('previewing')).toBe(true)
    fireEvent.mouseOut(el().querySelector('.dot')!, { relatedTarget: document.body })
    expect(el().classList.contains('previewing')).toBe(false)
  })
  it('previews on focus and hides on blur', () => {
    const { el } = setup()
    fireEvent.focusIn(el().querySelector('.dot')!)
    expect(el().classList.contains('previewing')).toBe(true)
    fireEvent.focusOut(el().querySelector('.dot')!, { relatedTarget: null })
    expect(el().classList.contains('previewing')).toBe(false)
  })
  it('previews while its tour is highlighted from elsewhere', () => {
    const { el, again } = setup({ highlighted: true })
    expect(el().classList.contains('previewing')).toBe(true)
    again({ highlighted: false })
    expect(el().classList.contains('previewing')).toBe(false)
  })
  it('raises a previewing dot above its neighbours', () => {
    const { el, again } = setup()
    const before = Number(el().style.zIndex)
    again({ highlighted: true })
    expect(Number(el().style.zIndex)).toBeGreaterThan(before + 5000)
  })
  it('activates on click and on Enter', () => {
    const { el, onActivate } = setup()
    fireEvent.click(el().querySelector('.dot')!)
    fireEvent.keyDown(el().querySelector('.dot')!, { key: 'Enter' })
    expect(onActivate).toHaveBeenCalledTimes(2)
  })
  it('does not keep a stuck preview when its html is replaced under the pointer', () => {
    const { el, again } = setup()
    fireEvent.mouseOver(el().querySelector('.dot')!)
    expect(el().classList.contains('previewing')).toBe(true)
    again({ html: dotHtml(bt(1), 'left') })
    expect(el().classList.contains('previewing')).toBe(false)
  })
})
