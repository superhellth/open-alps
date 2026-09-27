// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, waitFor, fireEvent } from '@testing-library/react'
import { MapContainer } from 'react-leaflet'
import RouteLayer from './RouteLayer.js'
import * as geometry from '@/tourSearch/loadLegGeometry.js'
import { opacity } from '@/ui/tokens.js'
import type { Route } from './types.js'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const route: Route = {
  waypoints: [{ lat: 47, lng: 11 }, { lat: 47.1, lng: 11.1 }, { lat: 47.2, lng: 11.2 }],
  legs: [{ edgeId: 5, reversed: false, layer: 'start_edges' }, { edgeId: -1, reversed: true, layer: 'hut_edges' }],
}

describe('RouteLayer', () => {
  it('fetches geometry only for legs that have an edge id', async () => {
    const spy = vi.spyOn(geometry, 'loadLegGeometry').mockResolvedValue([[47, 11], [47.05, 11.05]])
    render(<MapContainer center={[47, 11]} zoom={9}><RouteLayer route={route} /></MapContainer>)
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    expect(spy).toHaveBeenCalledWith('start_edges', 5, false)
  })
})

describe('RouteLayer tier and dots', () => {
  const draw = (props: Partial<Parameters<typeof RouteLayer>[0]> = {}) => {
    vi.spyOn(geometry, 'loadLegGeometry').mockResolvedValue([[47, 11], [47.05, 11.05]])
    return render(<MapContainer center={[47, 11]} zoom={9}><RouteLayer route={route} {...props} /></MapContainer>)
  }
  it('draws hut dots in the hovered symbol pane by default, as trip and saved views do', () => {
    const { container } = draw()
    expect(container.querySelectorAll('.leaflet-route-hovered-symbol-pane path').length).toBe(3)
  })
  it('draws no dots when dots is false', () => {
    const { container } = draw({ dots: false })
    expect(container.querySelectorAll('.leaflet-route-hovered-symbol-pane path').length).toBe(0)
  })
  it('draws the focused tier in its own panes', async () => {
    const { container } = draw({ tier: 'focused', thin: true, dots: false })
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-focused-line-pane path').length).toBeGreaterThan(0))
    expect(container.querySelectorAll('.leaflet-route-hovered-line-pane path').length).toBe(0)
  })
  it('reports the hovered leg index and position from the wide invisible hit line', async () => {
    const onHover = vi.fn()
    const { container } = draw({ tier: 'rest', thin: true, dots: false, onHover })
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-leg-hit-pane path').length).toBe(2))
    fireEvent.mouseOver(container.querySelector('.leaflet-route-leg-hit-pane path')!)
    expect(onHover).toHaveBeenCalledWith(true, expect.any(Number), expect.anything())
  })
  it('makes only the hit lines interactive, not the visible line', async () => {
    const { container } = draw()
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-hovered-line-pane path').length).toBe(2))
    expect(container.querySelectorAll('.leaflet-route-hovered-line-pane path.leaflet-interactive').length).toBe(0)
    expect(container.querySelectorAll('.leaflet-route-leg-hit-pane path.leaflet-interactive').length).toBe(2)
  })
  it('draws no hit lines for a display-only copy', async () => {
    const { container } = draw({ interactive: false })
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-hovered-line-pane path').length).toBeGreaterThan(0))
    expect(container.querySelectorAll('.leaflet-route-leg-hit-pane path').length).toBe(0)
  })
  it('dims every leg but the highlighted one', async () => {
    const { container } = draw({ highlightedLeg: 0, dots: false })
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-hovered-line-pane path').length).toBe(2))
    // Leg 0 has geometry (solid); leg 1 has none and is drawn as a dashed fallback.
    const paths = [...container.querySelectorAll('.leaflet-route-hovered-line-pane path')]
    const solid = paths.find((p) => !p.getAttribute('stroke-dasharray'))!
    const dashed = paths.find((p) => p.getAttribute('stroke-dasharray'))!
    expect(solid.getAttribute('stroke-opacity')).toBe('1')
    expect(dashed.getAttribute('stroke-opacity')).toBe(String(opacity.dimmed))
  })
  it('keeps every leg at full opacity when none is highlighted', async () => {
    const { container } = draw({ dots: false })
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-hovered-line-pane path').length).toBe(2))
    const opacities = [...container.querySelectorAll('.leaflet-route-hovered-line-pane path')].map((p) => p.getAttribute('stroke-opacity'))
    expect(opacities).toEqual(['1', '1'])
  })
  it('draws a cursor dot on the given leg and none without a cursor', async () => {
    const { container, rerender } = draw({ dots: false, cursor: { legIndex: 0, fraction: 0.5 } })
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-hovered-symbol-pane path').length).toBe(1))
    rerender(<MapContainer center={[47, 11]} zoom={9}><RouteLayer route={route} dots={false} cursor={null} /></MapContainer>)
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-hovered-symbol-pane path').length).toBe(0))
  })
})
