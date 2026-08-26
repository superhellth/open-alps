// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom/vitest'
import TourSearchPage from './TourSearchPage.js'
import * as tourSearchIndex from './tourSearch/index.js'
import type { GraphData, SearchResult } from './tourSearch/types.js'

const graphDataFixture: GraphData = {
  hutEdges: { hutIds: ['HutA'], variantNames: { 0: 'FAST_ANY' }, records: [] },
  approaches: { records: [], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } },
}

const searchResultFixture: SearchResult = {
  chains: [
    {
      huts: [0], startId: 100, exitStartId: 100,
      totalDurationH: 5, totalAscentM: 500, totalDescentM: 500, totalDistanceM: 8000,
      legs: [
        { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000 },
        { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000 },
      ],
    },
  ],
  killCounters: { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0 },
}

function fetchJsonMock(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response)
}

beforeEach(() => {
  vi.spyOn(tourSearchIndex, 'loadTourSearchData').mockResolvedValue(graphDataFixture)
  vi.spyOn(tourSearchIndex, 'findTours').mockReturnValue(searchResultFixture)
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.includes('huts.geojson')) {
        return fetchJsonMock({ type: 'FeatureCollection', features: [{ properties: { id: 0, name: 'HutA' }, geometry: { type: 'Point', coordinates: [11.0, 47.0] } }] })
      }
      if (url.includes('parking.geojson')) {
        return fetchJsonMock({
          type: 'FeatureCollection',
          features: [{ id: 'n100', properties: { name: 'Parkplatz Test' }, geometry: { type: 'Point', coordinates: [11.1, 47.1] } }],
        })
      }
      if (url.includes('stations.geojson')) {
        return fetchJsonMock({ type: 'FeatureCollection', features: [] })
      }
      throw new Error(`unexpected fetch ${url}`)
    }),
  )
})

describe('TourSearchPage', () => {
  it('loads data, submits the form, renders a result, and expanding it shows the route', async () => {
    render(<TourSearchPage />)

    await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: 'Touren suchen' }))

    await waitFor(() => expect(tourSearchIndex.findTours).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText(/1 Tour gefunden/)).toBeInTheDocument())

    await userEvent.click(screen.getByText(/Parkplatz Test/))
    await waitFor(() => expect(screen.getByText('Schematische Verbindung, nicht der reale Wegverlauf.')).toBeInTheDocument())
  })
})
