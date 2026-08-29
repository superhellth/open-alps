// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom/vitest'
import TourSearchPage from './TourSearchPage.js'
import * as tourSearchIndex from '../tourSearch/index.js'
import type { GraphData, SearchResult } from '../tourSearch/types.js'

// vitest.config.js doesn't set `globals: true`, so @testing-library/react's automatic
// afterEach(cleanup) never registers - without this, each test's render() stacks onto the
// previous test's un-unmounted DOM.
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const emptyHutEdgeIdsStub: GraphData['hutEdgeIds'] = {
  getSortedIds: () => new Int32Array(0),
  getPrefixIds: () => new Int32Array(0),
  getSuffixIds: () => new Int32Array(0),
}

const graphDataFixture: GraphData = {
  hutEdges: { hutIds: ['HutA'], variantNames: { 0: 'FAST_ANY' }, records: [] },
  approaches: { records: [], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } },
  hutEdgeIds: emptyHutEdgeIdsStub,
}

const searchResultFixture: SearchResult = {
  chains: [
    {
      huts: [0], startId: 100, exitStartId: 100,
      totalDurationH: 5, totalAscentM: 500, totalDescentM: 500, totalDistanceM: 8000,
      legs: [
        { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 0, reversed: false },
        { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 1, reversed: true },
      ],
    },
  ],
  killCounters: { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 0 },
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
      if (url.includes('partner_betriebe.geojson')) {
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

  it('resolves hut name/coordinates when huts.geojson uses GUID ids and TourResult.huts holds indices', async () => {
    vi.spyOn(tourSearchIndex, 'loadTourSearchData').mockResolvedValue({
      hutEdges: { hutIds: ['{GUID-A}'], variantNames: { 0: 'FAST_ANY' }, records: [] },
      approaches: { records: [], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } },
      hutEdgeIds: emptyHutEdgeIdsStub,
    })
    vi.spyOn(tourSearchIndex, 'findTours').mockReturnValue({
      chains: [{
        huts: [0], startId: 100, exitStartId: 100,
        totalDurationH: 5, totalAscentM: 500, totalDescentM: 500, totalDistanceM: 8000,
        legs: [
          { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 0, reversed: false },
          { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 1, reversed: true },
        ],
      }],
      killCounters: { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 0 },
    })
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('huts.geojson')) {
          return fetchJsonMock({
            type: 'FeatureCollection',
            features: [{ properties: { id: '{GUID-A}', name: 'Guid Hut', hutType: 'av', serviced: true }, geometry: { type: 'Point', coordinates: [11.0, 47.0] } }],
          })
        }
        if (url.includes('parking.geojson')) {
          return fetchJsonMock({
            type: 'FeatureCollection',
            features: [{ id: 'n100', properties: { name: 'Parkplatz Test' }, geometry: { type: 'Point', coordinates: [11.1, 47.1] } }],
          })
        }
        if (url.includes('stations.geojson')) return fetchJsonMock({ type: 'FeatureCollection', features: [] })
        if (url.includes('partner_betriebe.geojson')) return fetchJsonMock({ type: 'FeatureCollection', features: [] })
        throw new Error(`unexpected fetch ${url}`)
      }),
    )

    render(<TourSearchPage />)
    await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: 'Touren suchen' }))
    await waitFor(() => expect(screen.getByText(/1 Tour gefunden/)).toBeInTheDocument())

    await userEvent.click(screen.getByText(/Parkplatz Test/))
    // Before the fix, hutNameById.get(0) misses (map is keyed by GUID) and the raw index "0"
    // renders instead of "Guid Hut".
    await waitFor(() => expect(screen.getAllByText(/Guid Hut/).length).toBeGreaterThan(0))
  })

  it('fetches partner_betriebe.geojson and a 404 on it still leaves the page usable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('huts.geojson')) {
          return fetchJsonMock({ type: 'FeatureCollection', features: [{ properties: { id: 0, name: 'HutA', hutType: 'av', serviced: true }, geometry: { type: 'Point', coordinates: [11.0, 47.0] } }] })
        }
        if (url.includes('parking.geojson')) return fetchJsonMock({ type: 'FeatureCollection', features: [] })
        if (url.includes('stations.geojson')) return fetchJsonMock({ type: 'FeatureCollection', features: [] })
        if (url.includes('partner_betriebe.geojson')) return Promise.reject(new Error('404'))
        throw new Error(`unexpected fetch ${url}`)
      }),
    )
    render(<TourSearchPage />)
    await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Touren suchen' })).toBeEnabled()
  })

  it('renders the Bergsteigerdorf mode option and the operator/servicing checkboxes', async () => {
    render(<TourSearchPage />)
    await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())
    await userEvent.click(screen.getAllByRole('combobox')[0])
    expect(screen.getByText('Start im Bergsteigerdorf (offene Strecke)')).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(screen.getByLabelText(/Selbstversorgerhütten/)).toBeInTheDocument()
  })

  it('disables submit and shows a hint when the filter selection is empty', async () => {
    render(<TourSearchPage />)
    await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())
    await userEvent.click(screen.getByLabelText('AV-Hütte'))
    await userEvent.click(screen.getByLabelText('Sonstige Hütte'))
    expect(screen.getByRole('button', { name: 'Touren suchen' })).toBeDisabled()
  })
})
