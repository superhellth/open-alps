// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, waitFor, fireEvent } from '@testing-library/react'
import { MapContainer } from 'react-leaflet'
import RouteLayer from './RouteLayer.js'
import * as geometry from '@/tourSearch/loadLegGeometry.js'
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

describe('RouteLayer emphasis and dots', () => {
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
    const { container } = draw({ emphasis: 'focused', dots: false })
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-focused-line-pane path').length).toBeGreaterThan(0))
    expect(container.querySelectorAll('.leaflet-route-hovered-line-pane path').length).toBe(0)
  })
  it('reports the hovered leg index and position', async () => {
    const onHover = vi.fn()
    const { container } = draw({ emphasis: 'rest', dots: false, onHover })
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-rest-line-pane path').length).toBeGreaterThan(0))
    fireEvent.mouseOver(container.querySelector('.leaflet-route-rest-line-pane path')!)
    expect(onHover).toHaveBeenCalledWith(true, expect.any(Number), expect.anything())
  })
})
