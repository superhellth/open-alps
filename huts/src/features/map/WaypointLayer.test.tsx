// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { MapContainer } from 'react-leaflet'
import WaypointLayer from './WaypointLayer.js'
import { collectSymbols } from './waypointSymbols.js'
import type { Route, WaypointStop } from './types.js'

afterEach(cleanup)

const hut = (id: number): WaypointStop => ({ type: 'hut', hutId: id, operator: 'av', serviced: true })
const end = (id: number): WaypointStop => ({ type: 'end', startId: id, sourceType: 1 })
const route = (...stops: (WaypointStop | undefined)[]): Route => ({
  waypoints: stops.map((stop, i) => ({ lat: 47 + i * 0.01, lng: 11, stop })), legs: [],
})

describe('collectSymbols', () => {
  it('draws one symbol per unique hut across overlapping routes', () => {
    const s = collectSymbols([
      { route: route(end(1), hut(10), hut(11), end(1)), tier: 'rest' },
      { route: route(end(1), hut(10), hut(12), end(2)), tier: 'rest' },
    ])
    expect(s.map((x) => x.id).sort()).toEqual(['e1', 'e2', 'h10', 'h11', 'h12'])
  })
  it('takes the highest tier of the routes sharing a symbol', () => {
    const s = collectSymbols([
      { route: route(hut(10)), tier: 'rest' }, { route: route(hut(10)), tier: 'hovered' }, { route: route(hut(10)), tier: 'focused' },
    ])
    expect(s).toHaveLength(1)
    expect(s[0].tier).toBe('hovered')
  })
  it('skips waypoints without a stop (unclassified huts)', () => {
    expect(collectSymbols([{ route: route(undefined, hut(10)), tier: 'rest' }])).toHaveLength(1)
  })
})

describe('WaypointLayer', () => {
  const renderLayer = (symbols = collectSymbols([{ route: route(end(1), hut(10), hut(11)), tier: 'rest' }])) =>
    render(
      <MapContainer center={[47, 11]} zoom={13} style={{ height: 400, width: 400 }}>
        <WaypointLayer symbols={symbols} onHoverStop={() => {}} onClickStop={() => {}} />
      </MapContainer>,
    )
  it('draws a symbol per waypoint in the pane of its tier and a hit target per symbol', () => {
    const { container } = renderLayer()
    expect(container.querySelectorAll('.leaflet-route-rest-symbol-pane .leaflet-marker-icon')).toHaveLength(3)
    expect(container.querySelectorAll('.leaflet-route-hit-pane .leaflet-marker-icon')).toHaveLength(3)
  })
  it('does not make the visible symbols interactive', () => {
    const { container } = renderLayer()
    expect(container.querySelectorAll('.leaflet-route-rest-symbol-pane .leaflet-interactive')).toHaveLength(0)
  })
  it('draws a hovered hut with the selected (yellow) fill', () => {
    const { container } = renderLayer(collectSymbols([{ route: route(hut(10)), tier: 'hovered' }]))
    expect(container.querySelector('.leaflet-route-hovered-symbol-pane svg')!.innerHTML).toContain('#F5B700')
  })
})
