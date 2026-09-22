// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { MapContainer, TileLayer } from 'react-leaflet'
import SavedTripsLayer from './SavedTripsLayer.js'
import { newTrip } from '../../trip/trip.js'
import type { RouteContext } from '../routes.js'
import type { TripGraph } from '../../tourSearch/tripLegs.js'

afterEach(cleanup)

const graph: TripGraph = { hutEdges: { hutIds: ['{A}'], variantNames: {}, records: [] }, approaches: { records: [], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } } }
const routeCtx: RouteContext = { hutCoordsById: new Map([[0, { lat: 47.3, lng: 12 }]]), startById: new Map([[100, { lat: 47.2, lng: 12.1, name: 'Start', sourceType: 1 }]]), officialById: new Map() }
const trip = newTrip({ name: 'T', startDate: null, partySize: 1, start: { startId: 100, sourceType: 1 }, huts: ['{A}'], exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false } })

function renderLayer(props: Partial<Parameters<typeof SavedTripsLayer>[0]> = {}) {
  return render(
    <MapContainer center={[47.3, 12]} zoom={7}>
      <TileLayer url="" />
      <SavedTripsLayer
        active graph={graph} routeCtx={routeCtx} trips={[trip]} hoveredTripId={null} onHoverTrip={vi.fn()} onOpen={vi.fn()}
        {...props}
      />
    </MapContainer>,
  )
}

describe('SavedTripsLayer', () => {
  it('renders one route per resolvable trip', () => {
    const { container: empty } = renderLayer({ trips: [] })
    const baseline = empty.querySelectorAll('path').length
    const { container } = renderLayer()
    expect(container.querySelectorAll('path').length).toBeGreaterThan(baseline)
  })
  it('skips a trip that does not resolve on the graph', () => {
    const { container: empty } = renderLayer({ trips: [] })
    const baseline = empty.querySelectorAll('path').length
    const unresolvable = newTrip({ name: 'U', startDate: null, partySize: 1, start: { startId: 100, sourceType: 1 }, huts: ['{missing}'], exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false } })
    const { container } = renderLayer({ trips: [unresolvable] })
    expect(container.querySelectorAll('path').length).toBe(baseline)
  })
})
