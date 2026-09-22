// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { MapContainer } from 'react-leaflet'
import TripLayer from './TripLayer.js'

afterEach(cleanup)

function renderLayer(props: Partial<Parameters<typeof TripLayer>[0]> = {}) {
  return render(
    <MapContainer center={[47.3, 12]} zoom={12} style={{ height: 300, width: 300 }}>
      <TripLayer
        tripHuts={[]} tripEnds={[]} candidates={[]}
        hutCoordsById={new Map()} candidateStartCoords={new Map()}
        onPickCandidate={() => {}}
        {...props}
      />
    </MapContainer>,
  )
}

describe('TripLayer candidate markers', () => {
  it('renders a start-point candidate using its own coordinates, not hutCoordsById', () => {
    const onPickCandidate = vi.fn()
    const { container } = renderLayer({
      candidates: [{ startId: 5, sourceType: 1, legH: 2 }],
      candidateStartCoords: new Map([[5, { lat: 47.31, lng: 12.02 }]]),
      onPickCandidate,
    })
    expect(container.querySelectorAll('.swap-marker')).not.toHaveLength(0)
  })

  it('drops a start-point candidate silently when its coordinates are missing', () => {
    const { container } = renderLayer({
      candidates: [{ startId: 9, sourceType: 1, legH: 2 }],
      candidateStartCoords: new Map(),
    })
    expect(container.querySelectorAll('.swap-marker')).toHaveLength(0)
  })

  it('still renders a hut candidate from hutCoordsById', () => {
    const { container } = renderLayer({
      candidates: [{ hutIndex: 3, legH: 1.5 }],
      hutCoordsById: new Map([[3, { lat: 47.3, lng: 12 }]]),
    })
    expect(container.querySelectorAll('.swap-marker')).not.toHaveLength(0)
  })
})
