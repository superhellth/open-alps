// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import SavedTripsList from './SavedTripsList.js'
import { TripsProvider } from '@/trip/TripsProvider.js'
import { newTrip } from '@/trip/trip.js'
import { saveTrips } from '@/trip/tripStorage.js'
import type { TripGraph } from '@/tourSearch/types.js'

afterEach(cleanup)

const trip = (id: string, name: string) => newTrip({
  name, startDate: '2026-07-10', partySize: 2, start: { startId: 1, sourceType: 1 }, huts: ['{A}', '{B}'],
  exit: { startId: 1, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date('2026-06-01T00:00:00Z'), id)

const emptyGraph: TripGraph = { hutEdges: { hutIds: [], variantNames: {}, records: [] }, approaches: { records: [], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } } }

function memoryStorage() {
  const data: Record<string, string> = {}
  return { getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => { data[k] = v }, data }
}
function renderWith(
  trips = [trip('a', 'Kaiser'), trip('b', 'Wetterstein')],
  draft: ReturnType<typeof trip> | null = null,
  overrides: Partial<Parameters<typeof SavedTripsList>[0]> = {},
) {
  const storage = memoryStorage()
  saveTrips({ trips, activeId: null, draft, activeIsDraft: draft !== null }, storage)
  const props = {
    graph: emptyGraph, onOpen: vi.fn(), onOpenDraft: vi.fn(), onPlanen: vi.fn(), hoveredTripId: null, onHoverTrip: vi.fn(), ...overrides,
  }
  render(<TripsProvider storage={storage}><SavedTripsList {...props} /></TripsProvider>)
  return { storage, ...props }
}

function openMenu(id: string) {
  fireEvent.click(within(screen.getByTestId(`trip-${id}`)).getByLabelText('Weitere Aktionen'))
}

describe('SavedTripsList', () => {
  it('lists saved trips with dates and night count', () => {
    renderWith()
    expect(screen.getByText('Kaiser')).toBeInTheDocument()
    expect(screen.getAllByText(/2 Nächte/).length).toBe(2)
  })
  it('lists only saved trips, never the draft', () => {
    renderWith([trip('a', 'Saved Trip')], trip('d', 'Draft Trip'))
    expect(screen.getByText('Saved Trip')).toBeInTheDocument()
    expect(screen.queryByText('Draft Trip')).not.toBeInTheDocument()
  })
  it('says so when there are none', () => {
    renderWith([])
    expect(screen.getByText('Noch keine Touren gespeichert.')).toBeInTheDocument()
  })
  it('a row calls onOpen with its id', () => {
    const { onOpen } = renderWith()
    fireEvent.click(screen.getByText('Kaiser'))
    expect(onOpen).toHaveBeenCalledWith('a')
  })
  it('shows a booking summary', () => {
    renderWith()
    expect(screen.getAllByText(/0\/2 bestätigt/).length).toBe(2)
  })
  it('the ⋮ menu offers Umbenennen and Löschen', () => {
    renderWith()
    openMenu('a')
    expect(screen.getByText('Umbenennen')).toBeInTheDocument()
    expect(screen.getByText('Löschen')).toBeInTheDocument()
  })
  it('deletes with an undo that brings the trip back', () => {
    renderWith()
    openMenu('a')
    fireEvent.click(screen.getByText('Löschen'))
    expect(screen.queryByText('Kaiser')).not.toBeInTheDocument()
  })
  it('renames via the menu', () => {
    renderWith()
    openMenu('a')
    fireEvent.click(screen.getByText('Umbenennen'))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Kaisertour 2026' } })
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(screen.getByText('Kaisertour 2026')).toBeInTheDocument()
  })
  it('imports a backup and reports an unreadable file', async () => {
    renderWith([])
    fireEvent.click(screen.getAllByLabelText('Weitere Aktionen')[0])
    const input = screen.getByLabelText('Touren importieren') as HTMLInputElement
    const good = new File([JSON.stringify({ trips: [trip('z', 'Importiert')] })], 'b.json', { type: 'application/json' })
    fireEvent.change(input, { target: { files: [good] } })
    expect(await screen.findByText('Importiert')).toBeInTheDocument()
    fireEvent.click(screen.getAllByLabelText('Weitere Aktionen')[0])
    const input2 = screen.getByLabelText('Touren importieren') as HTMLInputElement
    const bad = new File(['nope'], 'b.json')
    fireEvent.change(input2, { target: { files: [bad] } })
    expect(await screen.findByText('Die Datei enthält keine gültigen Touren.')).toBeInTheDocument()
  })
  it('opens the pinned draft row', () => {
    const { onOpenDraft } = renderWith([trip('a', 'Kaiser')], trip('d', 'Draft Trip'))
    fireEvent.click(screen.getByText('Ungespeicherte Tour · öffnen'))
    expect(onOpenDraft).toHaveBeenCalled()
  })
  it('flags a trip with an unresolved hut as geändert', () => {
    renderWith()
    expect(screen.getAllByText('geändert').length).toBeGreaterThan(0)
  })
  it('the empty state links back to Planen', () => {
    const { onPlanen } = renderWith([])
    fireEvent.click(screen.getByText('Tour planen'))
    expect(onPlanen).toHaveBeenCalled()
  })
})
