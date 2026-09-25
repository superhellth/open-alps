// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import PlannerPage from './PlannerPage.js'
import { AppDataProvider } from '@/data/AppDataProvider.js'
import { SearchClientProvider } from '@/search/SearchClientProvider.js'
import { TripsProvider } from '@/trip/TripsProvider.js'
import { makeTestAppData } from '@/testing/testAppData.js'
import type { WorkerLike } from '@/search/searchClient.js'
import type { TourResult } from '@/tourSearch/types.js'
import * as availability from '@/availability/fetchAvailability.js'
import * as detail from '@/availability/fetchHutDetail.js'
import { newTrip } from '@/trip/trip.js'
import { saveTrips } from '@/trip/tripStorage.js'

vi.mock('@/tourSearch/loadLegElevation.js', () => ({
  loadLegElevation: vi.fn(async () => [1000, 1050, 1020]),
}))

beforeEach(() => {
  localStorage.setItem('open-alps.prompt-seen', '1')
  vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
  vi.spyOn(detail, 'fetchHutDetail').mockResolvedValue({ hutId: 1, hutName: '', calendarDays: [] })
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear(); window.location.hash = '' })

const data = makeTestAppData()
const chain: TourResult = {
  huts: [0], startId: 100, exitStartId: 100, totalDurationH: 9, totalAscentM: 900, totalDescentM: 900, totalDistanceM: 12000,
  legs: [
    { durationH: 4.5, ascentM: 450, descentM: 0, distanceM: 6000, edgeId: 0, reversed: false },
    { durationH: 4.5, ascentM: 0, descentM: 450, distanceM: 6000, edgeId: 0, reversed: true },
  ],
}

function fakeWorker(): WorkerLike {
  const worker: WorkerLike = {
    onmessage: null, onerror: null, terminate: () => {},
    postMessage(m) {
      if (m.type === 'search') queueMicrotask(() => worker.onmessage?.({ data: { type: 'result', id: m.id, chains: [chain] } }))
      else queueMicrotask(() => worker.onmessage?.({ data: { type: 'overlaps', id: m.id, pairs: [] } }))
    },
  }
  queueMicrotask(() => worker.onmessage?.({ data: { type: 'ready' } }))
  return worker
}
const makeWorker = () => fakeWorker()
const load = () => Promise.resolve(data)

function renderPlanner() {
  return render(
    <AppDataProvider load={load}>
      <SearchClientProvider makeWorker={makeWorker}>
        <TripsProvider storage={null}>
          <PlannerPage importHash={null} />
        </TripsProvider>
      </SearchClientProvider>
    </AppDataProvider>,
  )
}

function memoryStorage() {
  const data: Record<string, string> = {}
  return { getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => { data[k] = v }, data }
}

function renderPlannerWithSavedTrip() {
  const storage = memoryStorage()
  const trip = newTrip({
    name: 'Kaiser', startDate: '2026-07-10', partySize: 2, start: { startId: 100, sourceType: 1 }, huts: ['{A}'],
    exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
  }, new Date('2026-06-01T00:00:00Z'), 'a')
  saveTrips({ trips: [trip], activeId: null, draft: null, activeIsDraft: false }, storage)
  return render(
    <AppDataProvider load={load}>
      <SearchClientProvider makeWorker={makeWorker}>
        <TripsProvider storage={storage}>
          <PlannerPage importHash={null} />
        </TripsProvider>
      </SearchClientProvider>
    </AppDataProvider>,
  )
}

/** A count bubble only focuses the results list; the tour opens from its list row. */
async function openFirstResult(container: HTMLElement) {
  await waitFor(() => expect(container.querySelector('.start-count-marker')).not.toBeNull(), { timeout: 5000 })
  fireEvent.click(container.querySelector('.start-count-marker')!)
  fireEvent.click(await screen.findByRole('button', { name: /Hütte A/ }))
}

describe('PlannerPage', () => {
  it('shows a loading view and no filter bar while app data loads', () => {
    render(
      <AppDataProvider load={() => new Promise(() => {})}>
        <SearchClientProvider makeWorker={makeWorker}>
          <TripsProvider storage={null}>
            <PlannerPage importHash={null} />
          </TripsProvider>
        </SearchClientProvider>
      </AppDataProvider>,
    )
    expect(screen.getByText(/Daten werden geladen/)).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Filter' })).toBeNull()
  })

  it('shows the load error as an alert', async () => {
    render(
      <AppDataProvider load={() => Promise.reject(new Error('kaputt'))}>
        <SearchClientProvider makeWorker={makeWorker}>
          <TripsProvider storage={null}>
            <PlannerPage importHash={null} />
          </TripsProvider>
        </SearchClientProvider>
      </AppDataProvider>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('kaputt')
  })

  it('discover -> pick -> trip -> back, opening the pick as a draft', async () => {
    const { container } = renderPlanner()
    expect(screen.getByText('Daten werden geladen ...')).toBeInTheDocument()

    // The search finishes and start point 100 shows one matching tour.
    await waitFor(() => expect(container.querySelector('.start-count-marker')).not.toBeNull(), { timeout: 5000 })
    expect(container.querySelectorAll('.start-count-marker')).toHaveLength(1)

    await openFirstResult(container)

    // The trip panel replaces the results column, opened as a draft.
    expect(await screen.findByRole('button', { name: '← Ergebnisse' })).toBeInTheDocument()
    expect(screen.getAllByText('Hütte A').length).toBeGreaterThan(0)
    expect(screen.getByText('Entwurf')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '← Ergebnisse' }))
    expect(await screen.findByRole('button', { name: /Hütte A/ })).toBeInTheDocument()
  })

  it('asks before replacing a dirty draft, and discards on confirm', async () => {
    const { container } = renderPlanner()
    await openFirstResult(container)
    expect(await screen.findByText('Entwurf')).toBeInTheDocument()

    fireEvent.click(screen.getByText(/· 1 Pers\./))
    const partyFields = screen.getAllByLabelText('Personen')
    const visible = partyFields.find((el) => !el.closest('[hidden]'))!
    fireEvent.change(visible, { target: { value: '4' } })
    fireEvent.keyDown(visible, { key: 'Escape', code: 'Escape' })

    fireEvent.click(screen.getByRole('button', { name: '← Ergebnisse' }))
    const row = await screen.findByRole('button', { name: /Hütte A/ })
    fireEvent.click(row)

    expect(screen.getByText('Entwurf verwerfen?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Verwerfen' }))
    await waitFor(() => expect(screen.queryByText('Entwurf verwerfen?')).not.toBeInTheDocument())
    expect(screen.getByText('Entwurf')).toBeInTheDocument()
  })

  it('replaces an unedited draft silently on a new pick', async () => {
    const { container } = renderPlanner()
    await openFirstResult(container)
    fireEvent.click(screen.getByRole('button', { name: '← Ergebnisse' }))
    const row = await screen.findByRole('button', { name: /Hütte A/ })
    fireEvent.click(row)
    expect(screen.queryByText('Entwurf verwerfen?')).not.toBeInTheDocument()
  })

  it('Speichern moves the draft into saved trips and clears the Entwurf badge', async () => {
    const { container } = renderPlanner()
    await openFirstResult(container)
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(screen.queryByText('Entwurf')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toBeInTheDocument()
  })

  it('shows the fixed no-match hint and no markers when nothing matches', async () => {
    const empty: WorkerLike = (() => {
      const w: WorkerLike = {
        onmessage: null, onerror: null, terminate: () => {},
        postMessage(m) { queueMicrotask(() => w.onmessage?.({ data: { type: 'result', id: m.id, chains: [] } })) },
      }
      return w
    })()
    const { container } = render(
      <AppDataProvider load={load}>
        <SearchClientProvider makeWorker={() => empty}>
          <TripsProvider storage={null}><PlannerPage importHash={null} /></TripsProvider>
        </SearchClientProvider>
      </AppDataProvider>,
    )
    expect(await screen.findByText('Keine Touren für diese Filter. Mehr Tage oder längere Gehzeit pro Tag zulassen.')).toBeInTheDocument()
    expect(container.querySelectorAll('.start-count-marker')).toHaveLength(0)
  })

  it('lists the matching tours on the Ergebnisse tab without picking a marker', async () => {
    renderPlanner()
    fireEvent.click(await screen.findByRole('tab', { name: /Ergebnisse/ }))
    expect(await screen.findByRole('button', { name: /Hütte A/ })).toBeInTheDocument()
  })

  it('the map status bar cancels the active candidate mode', async () => {
    const { container } = renderPlanner()
    await openFirstResult(container)
    fireEvent.click(screen.getByLabelText('Weitere Aktionen Etappe 1'))
    fireEvent.click(screen.getByText('Hütte tauschen'))
    const label = await screen.findByText('Neue Hütte für Etappe 1 wählen')
    const statusBar = label.parentElement!
    fireEvent.click(within(statusBar).getByRole('button', { name: 'Abbrechen' }))
    await waitFor(() => expect(screen.queryByText('Neue Hütte für Etappe 1 wählen')).not.toBeInTheDocument())
  })

  it('hovering a stage row highlights the matching leg on the height profile', async () => {
    const { container } = renderPlanner()
    await openFirstResult(container)
    const stage = await waitFor(() => {
      const el = container.querySelector('[data-stage="0"]')
      if (!el) throw new Error('stage not rendered yet')
      return el
    })
    fireEvent.mouseEnter(stage)
    await waitFor(() => expect(screen.getByTestId('leg-segment-0')).toHaveAttribute('data-highlighted', 'true'))
  })

  it('offers to import a shared trip from a share link', async () => {
    const { encodeTripToHash } = await import('@/trip/shareLink.js')
    const { newTrip } = await import('@/trip/trip.js')
    const shared = newTrip({
      name: 'Aus Link', startDate: null, partySize: 1, start: { startId: 100, sourceType: 1 }, huts: ['{A}'],
      exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
    })
    render(
      <AppDataProvider load={load}>
        <SearchClientProvider makeWorker={makeWorker}>
          <TripsProvider storage={null}><PlannerPage importHash={encodeTripToHash(shared)} /></TripsProvider>
        </SearchClientProvider>
      </AppDataProvider>,
    )
    expect(await screen.findByText('Aus Link')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'In meine Touren übernehmen' }))
    expect(await screen.findByRole('button', { name: '← Ergebnisse' })).toBeInTheDocument()
  })

  it('#trips shows the saved-trips list', async () => {
    window.location.hash = '#trips'
    renderPlanner()
    expect(await screen.findByText('Meine Touren')).toBeInTheDocument()
  })

  it('opening a trip from the saved list back-navigates to Meine Touren', async () => {
    window.location.hash = '#trips'
    renderPlannerWithSavedTrip()
    fireEvent.click(await screen.findByText('Kaiser'))
    expect(await screen.findByRole('button', { name: '← Meine Touren' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '← Meine Touren' }))
    expect(window.location.hash).toBe('#trips')
    expect(await screen.findByText('Meine Touren')).toBeInTheDocument()
  })

  it('switching to Meine Touren while a draft trip is open keeps the draft pinned', async () => {
    const { container } = renderPlanner()
    await openFirstResult(container)
    expect(await screen.findByText('Entwurf')).toBeInTheDocument()
    fireEvent.click(screen.getByText(/Meine Touren/))
    expect(await screen.findByText('Entwurf · nicht gespeichert')).toBeInTheDocument()
  })
})
