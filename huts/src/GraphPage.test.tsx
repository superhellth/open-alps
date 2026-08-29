// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom/vitest'
import GraphPage from './GraphPage.js'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function fetchJsonMock(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response)
}

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.includes('hut-edge-stats.json')) return fetchJsonMock([])
      if (url.includes('hut-edge-geometry.json')) return fetchJsonMock({ point_counts: [] })
      if (url.includes('hut-edge-geometry.bin')) return Promise.resolve({ arrayBuffer: () => Promise.resolve(new ArrayBuffer(0)) } as unknown as Response)
      if (url.includes('huts.geojson')) {
        return fetchJsonMock({
          type: 'FeatureCollection',
          features: [
            { properties: { id: 1, name: 'AV Hut', hutType: 'av', serviced: true }, geometry: { type: 'Point', coordinates: [11.0, 47.0] } },
            { properties: { id: 2, name: 'Sonstige SV Hut', hutType: 'sonstige', serviced: false }, geometry: { type: 'Point', coordinates: [11.1, 47.1] } },
          ],
        })
      }
      if (url.includes('partner_betriebe.geojson')) {
        return fetchJsonMock({
          type: 'FeatureCollection',
          features: [{ properties: { id: 30, name: 'FeWo Test' }, geometry: { type: 'Point', coordinates: [11.2, 47.2] } }],
        })
      }
      throw new Error(`unexpected fetch ${url}`)
    }),
  )
}

describe('GraphPage hut classification', () => {
  it('renders a checkbox group and dims non-matching markers without hiding them', async () => {
    stubFetch()
    const { container } = render(<GraphPage />)
    await waitFor(() => expect(screen.getByText(/2 Hütten/)).toBeInTheDocument())

    const markersBefore = container.querySelectorAll('path.leaflet-interactive')
    const countBefore = markersBefore.length

    await userEvent.click(screen.getByLabelText('Sonstige Hütte'))

    const markersAfter = container.querySelectorAll('path.leaflet-interactive')
    // Dimming must not remove markers from the DOM.
    expect(markersAfter.length).toBe(countBefore)
  })

  it('a 404 on partner_betriebe.geojson still leaves the graph page usable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('hut-edge-stats.json')) return fetchJsonMock([])
        if (url.includes('hut-edge-geometry.json')) return fetchJsonMock({ point_counts: [] })
        if (url.includes('hut-edge-geometry.bin')) return Promise.resolve({ arrayBuffer: () => Promise.resolve(new ArrayBuffer(0)) } as unknown as Response)
        if (url.includes('huts.geojson')) return fetchJsonMock({ type: 'FeatureCollection', features: [] })
        if (url.includes('partner_betriebe.geojson')) return Promise.reject(new Error('404'))
        throw new Error(`unexpected fetch ${url}`)
      }),
    )
    render(<GraphPage />)
    await waitFor(() => expect(screen.getByText(/0 Hütten/)).toBeInTheDocument())
  })
})
