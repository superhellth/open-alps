// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import PlannerPage from './PlannerPage.js'
import { AppDataProvider } from '../data/AppDataProvider.js'
import { SearchClientProvider } from '../search/SearchClientProvider.js'
import { TripsProvider } from '../trip/TripsProvider.js'
import { makeTestAppData } from './testAppData.js'
import type { WorkerLike } from '../search/searchClient.js'
import type { TourResult } from '../tourSearch/types.js'
import * as availability from '../availability/fetchAvailability.js'
import * as detail from '../availability/fetchHutDetail.js'

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

async function openFirstResult(container: HTMLElement) {
  await waitFor(() => expect(container.querySelector('.start-count-marker')).not.toBeNull())
  fireEvent.click(container.querySelector('.start-count-marker')!)
  const row = await screen.findByRole('button', { name: /Hütte A/ })
  fireEvent.click(row)
}

describe('PlannerPage', () => {
  it('discover -> pick -> trip -> back, opening the pick as a draft', async () => {
    const { container } = renderPlanner()
    expect(screen.getByText('Wegenetz wird geladen …')).toBeInTheDocument()

    // The search finishes and start point 100 shows one matching tour.
    await waitFor(() => expect(container.querySelector('.start-count-marker')).not.toBeNull())
    expect(container.querySelector('.start-count-marker span')?.textContent).toBe('1')

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

    fireEvent.click(screen.getByText(/ohne Datum · 1 Pers\./))
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

  it('clicking "N Touren anzeigen" selects the best cluster', async () => {
    const { container } = renderPlanner()
    await waitFor(() => expect(container.querySelector('.start-count-marker')).not.toBeNull())
    fireEvent.click(screen.getByRole('button', { name: /Touren anzeigen/ }))
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

  it('offers to import a shared trip from a share link', async () => {
    const { encodeTripToHash } = await import('../trip/shareLink.js')
    const { newTrip } = await import('../trip/trip.js')
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
})
