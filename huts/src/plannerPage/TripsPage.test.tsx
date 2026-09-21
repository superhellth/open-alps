// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import TripsPage from './TripsPage.js'
import { TripsProvider } from '../trip/TripsProvider.js'
import { newTrip } from '../trip/trip.js'
import { saveTrips } from '../trip/tripStorage.js'

afterEach(() => { cleanup(); window.location.hash = '' })

const trip = (id: string, name: string) => newTrip({
  name, startDate: '2026-07-10', partySize: 2, start: { startId: 1, sourceType: 1 }, huts: ['{A}', '{B}'],
  exit: { startId: 1, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date('2026-06-01T00:00:00Z'), id)

function memoryStorage() {
  const data: Record<string, string> = {}
  return { getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => { data[k] = v }, data }
}
function renderWith(trips = [trip('a', 'Kaiser'), trip('b', 'Wetterstein')]) {
  const storage = memoryStorage()
  saveTrips({ trips, activeId: null }, storage)
  render(<TripsProvider storage={storage}><TripsPage /></TripsProvider>)
  return storage
}

describe('TripsPage', () => {
  it('lists saved trips with dates and night count', () => {
    renderWith()
    expect(screen.getByText('Kaiser')).toBeInTheDocument()
    expect(screen.getAllByText(/2 Nächte/).length).toBe(2)
  })
  it('says so when there are none', () => {
    renderWith([])
    expect(screen.getByText('Noch keine Touren gespeichert.')).toBeInTheDocument()
  })
  it('opening a trip makes it active and goes to the planner', () => {
    const storage = renderWith()
    fireEvent.click(within(screen.getByTestId('trip-a')).getByRole('button', { name: 'Öffnen' }))
    expect(JSON.parse(storage.data['open-alps.trips.v1']).activeId).toBe('a')
    expect(window.location.hash).toBe('')
  })
  it('deletes with an undo that brings the trip back', () => {
    renderWith()
    fireEvent.click(within(screen.getByTestId('trip-a')).getByRole('button', { name: 'Löschen' }))
    expect(screen.queryByText('Kaiser')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Rückgängig' }))
    expect(screen.getByText('Kaiser')).toBeInTheDocument()
  })
  it('renames inline', () => {
    renderWith()
    fireEvent.click(within(screen.getByTestId('trip-a')).getByRole('button', { name: 'Umbenennen' }))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Kaisertour 2026' } })
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(screen.getByText('Kaisertour 2026')).toBeInTheDocument()
  })
  it('imports a backup and reports an unreadable file', async () => {
    renderWith([])
    const input = screen.getByLabelText('Sicherung importieren') as HTMLInputElement
    const good = new File([JSON.stringify({ trips: [trip('z', 'Importiert')] })], 'b.json', { type: 'application/json' })
    fireEvent.change(input, { target: { files: [good] } })
    expect(await screen.findByText('Importiert')).toBeInTheDocument()
    const bad = new File(['nope'], 'b.json')
    fireEvent.change(input, { target: { files: [bad] } })
    expect(await screen.findByText('Die Datei enthält keine gültige Sicherung.')).toBeInTheDocument()
  })
})
