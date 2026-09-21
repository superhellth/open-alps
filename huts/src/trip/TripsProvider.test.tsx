// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { TripsProvider, useTrips } from './TripsProvider.js'
import { newTrip } from './trip.js'
import { saveTrips } from './tripStorage.js'

afterEach(cleanup)

const trip = (id: string) => newTrip({
  name: id, startDate: null, partySize: 1, start: { startId: 1, sourceType: 1 }, huts: ['{A}'],
  exit: { startId: 1, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date('2026-06-01T00:00:00Z'), id)

function memoryStorage() {
  const data: Record<string, string> = {}
  return { getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => { data[k] = v }, data }
}

function Probe() {
  const { state, dispatch, activeTrip } = useTrips()
  return (
    <div>
      <span>count:{state.trips.length}</span>
      <span>active:{activeTrip?.name ?? 'none'}</span>
      <button onClick={() => dispatch({ type: 'create', trip: trip('neu') })}>create</button>
    </div>
  )
}

describe('TripsProvider', () => {
  it('starts from what is in storage', () => {
    const storage = memoryStorage()
    saveTrips({ trips: [trip('alt')], activeId: 'alt' }, storage)
    render(<TripsProvider storage={storage}><Probe /></TripsProvider>)
    expect(screen.getByText('count:1')).toBeInTheDocument()
    expect(screen.getByText('active:alt')).toBeInTheDocument()
  })
  it('persists every change', () => {
    const storage = memoryStorage()
    render(<TripsProvider storage={storage}><Probe /></TripsProvider>)
    fireEvent.click(screen.getByText('create'))
    expect(JSON.parse(storage.data['open-alps.trips.v1']).trips).toHaveLength(1)
  })
  it('works without any storage', () => {
    render(<TripsProvider storage={null}><Probe /></TripsProvider>)
    fireEvent.click(screen.getByText('create'))
    expect(screen.getByText('count:1')).toBeInTheDocument()
  })
})
