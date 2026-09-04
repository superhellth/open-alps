// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom/vitest'
import TourSearchPage from './TourSearchPage.js'
import * as tourSearchIndex from '../tourSearch/index.js'
import * as availability from '../availability/fetchAvailability.js'
import type { GraphData, SearchResult } from '../tourSearch/types.js'
import { packColumns } from '../tourSearch/binaryColumns.js'

const emptyTourEdgePayload = packColumns(
  { tour_id: 'u1', leg_index: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4', max_ele_m: 'f4', sac_rank: 'i1', via_ferrata: 'u1' },
  { tour_id: [], leg_index: [], distance_m: [], ascent_m: [], descent_m: [], max_ele_m: [], sac_rank: [], via_ferrata: [] },
  0,
)

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
  startEdgeIds: emptyHutEdgeIdsStub,
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
  killCounters: { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 0, trackOverlap: 0, availability: 0 },
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
        return fetchJsonMock({
          type: 'FeatureCollection',
          features: [{ properties: { id: 'HutA', name: 'HutA', hutType: 'av', serviced: true, ohrsHutId: '179', tenantCode: 8 }, geometry: { type: 'Point', coordinates: [11.0, 47.0] } }],
        })
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
      if (url.includes('tours.json')) return fetchJsonMock([])
      if (url.includes('tour-edge-payload.json')) return fetchJsonMock(emptyTourEdgePayload.manifest)
      if (url === '/data/tour-edge-payload.bin') {
        return Promise.resolve({ arrayBuffer: () => Promise.resolve(emptyTourEdgePayload.buffer) } as Response)
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
      startEdgeIds: emptyHutEdgeIdsStub,
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
      killCounters: { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 0, trackOverlap: 0, availability: 0 },
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
        if (url.includes('tours.json')) return fetchJsonMock([])
        if (url.includes('tour-edge-payload.json')) return fetchJsonMock(emptyTourEdgePayload.manifest)
        if (url === '/data/tour-edge-payload.bin') {
          return Promise.resolve({ arrayBuffer: () => Promise.resolve(emptyTourEdgePayload.buffer) } as Response)
        }
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
        if (url.includes('tours.json')) return fetchJsonMock([])
        if (url.includes('tour-edge-payload.json')) return fetchJsonMock(emptyTourEdgePayload.manifest)
        if (url === '/data/tour-edge-payload.bin') {
          return Promise.resolve({ arrayBuffer: () => Promise.resolve(emptyTourEdgePayload.buffer) } as Response)
        }
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

  it('fetches availability when a start date is set and shows a free-bed badge on the result hut', async () => {
    vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map([[1, new Set(['179'])]]))

    render(<TourSearchPage />)
    await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())

    await userEvent.type(screen.getByLabelText(/Startdatum/), '2026-08-20')
    await userEvent.click(screen.getByRole('button', { name: 'Touren suchen' }))

    await waitFor(() => expect(availability.fetchAvailabilityByOffset).toHaveBeenCalledWith(new Date('2026-08-20'), 1, 3))
    await waitFor(() => expect(screen.getByText(/1 Tour gefunden/)).toBeInTheDocument())

    await userEvent.click(screen.getByText(/Parkplatz Test/))
    await waitFor(() => expect(screen.getByText('frei')).toBeInTheDocument())
  })

  it('the "nur Touren mit Verfügbarkeit" checkbox is hidden until a start date is picked', async () => {
    render(<TourSearchPage />)
    await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())
    expect(screen.queryByLabelText(/nur Touren mit Verfügbarkeit/)).not.toBeInTheDocument()

    await userEvent.type(screen.getByLabelText(/Startdatum/), '2026-08-20')
    expect(screen.getByLabelText(/nur Touren mit Verfügbarkeit/)).toBeInTheDocument()
  })

  it('toggling to "Offizielle Touren" hides the filter form and shows an official-tour card, preserving search results underneath', async () => {
    const officialTour = {
      tourId: 1, name: 'Welser Höhenweg',
      legs: [{ legIndex: 0, from: { type: 'hut', id: 0 }, to: { type: 'parking', id: 100 } }],
    }
    const tourEdgePayload = packColumns(
      { tour_id: 'u1', leg_index: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4', max_ele_m: 'f4', sac_rank: 'i1', via_ferrata: 'u1' },
      { tour_id: [1], leg_index: [0], distance_m: [5000], ascent_m: [400], descent_m: [100], max_ele_m: [1800], sac_rank: [2], via_ferrata: [0] },
      1,
    )
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('huts.geojson')) {
          return fetchJsonMock({
            type: 'FeatureCollection',
            features: [{ properties: { id: 'HutA', name: 'HutA', hutType: 'av', serviced: true }, geometry: { type: 'Point', coordinates: [11.0, 47.0] } }],
          })
        }
        if (url.includes('parking.geojson')) {
          return fetchJsonMock({ type: 'FeatureCollection', features: [{ id: 'n100', properties: { name: 'Parkplatz Test' }, geometry: { type: 'Point', coordinates: [11.1, 47.1] } }] })
        }
        if (url.includes('stations.geojson')) return fetchJsonMock({ type: 'FeatureCollection', features: [] })
        if (url.includes('partner_betriebe.geojson')) return fetchJsonMock({ type: 'FeatureCollection', features: [] })
        if (url.includes('tours.json')) return fetchJsonMock([officialTour])
        if (url.includes('tour-edge-payload.json')) return fetchJsonMock(tourEdgePayload.manifest)
        if (url === '/data/tour-edge-payload.bin') return Promise.resolve({ arrayBuffer: () => Promise.resolve(tourEdgePayload.buffer) } as Response)
        throw new Error(`unexpected fetch ${url}`)
      }),
    )

    render(<TourSearchPage />)
    await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: 'Touren suchen' }))
    await waitFor(() => expect(screen.getByText(/1 Tour gefunden/)).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: 'Offizielle Touren' }))

    expect(screen.queryByText('Modus')).not.toBeInTheDocument()
    expect(screen.getByText('Welser Höhenweg')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Freie Suche' }))
    expect(screen.getByText(/1 Tour gefunden/)).toBeInTheDocument()
  })

  it('shows the official-tours empty-state message (no spinner wording) when the list is empty', async () => {
    render(<TourSearchPage />)
    await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: 'Offizielle Touren' }))
    await waitFor(() => expect(screen.getByText(/keine durchgehend berechneten Routen/)).toBeInTheDocument())
  })
})
