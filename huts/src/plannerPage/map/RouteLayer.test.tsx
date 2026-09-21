// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, waitFor } from '@testing-library/react'
import { MapContainer } from 'react-leaflet'
import RouteLayer from './RouteLayer.js'
import * as geometry from '../../tourSearch/loadLegGeometry.js'
import type { Route } from '../types.js'

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
