// @vitest-environment jsdom
import { it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import AvailabilityDetailPanel from './AvailabilityDetailPanel.js'
import * as fetchHutDetailModule from '../availability/fetchHutDetail.js'
import type { TourResult } from '../tourSearch/types.js'
import type { HutDetail } from '../availability/types.js'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const chain: TourResult = {
  huts: [0], startId: 100, exitStartId: 100,
  totalDurationH: 5, totalAscentM: 500, totalDescentM: 500, totalDistanceM: 8000,
  legs: [
    { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 0, reversed: false },
    { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 1, reversed: true },
  ],
}
const hutNameById = new Map([[0, 'Pfeis-Hütte']])
const hutOhrsByIndex = new Map([[0, { ohrsHutId: '179', tenantCode: 8 }]])

it('fetches detail for each hut with an ohrsHutId and renders its bed categories', async () => {
  const detail: HutDetail = {
    hutId: 179, hutName: 'Pfeis-Hütte',
    calendarDays: [{
      day: '20.08.2026', reservationMode: 'SERVICED', status: 'RESERVATION_POSSIBLE',
      bedCategoriesData: [{ totalPlaces: 37, occupation: 'MEDIUM', totalFreePlaces: 5, label: 'Matratzenlager' }],
    }],
  }
  vi.spyOn(fetchHutDetailModule, 'fetchHutDetail').mockResolvedValue(detail)

  render(
    <AvailabilityDetailPanel
      chain={chain} hutNameById={hutNameById} hutOhrsByIndex={hutOhrsByIndex}
      startDate={new Date(Date.UTC(2026, 7, 20))} numOfPeople={2}
    />,
  )

  expect(fetchHutDetailModule.fetchHutDetail).toHaveBeenCalledWith('179', 8, new Date(Date.UTC(2026, 7, 20)), 2)
  await waitFor(() => expect(screen.getByText('Matratzenlager')).toBeInTheDocument())
  expect(screen.getByText('5')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /hut-reservation.org/ })).toHaveAttribute(
    'href', 'https://www.hut-reservation.org/reservation/book-hut/179/wizard?dateFrom=20.08.2026&dateTo=21.08.2026',
  )
})

it('shows the German reason text for a closed-for-season hut', async () => {
  const detail: HutDetail = {
    hutId: 520, hutName: 'Würgauer Haus',
    calendarDays: [{ day: '20.08.2026', reservationMode: 'CLOSED', status: 'HUT_CLOSED_TO_PUBLIC', bedCategoriesData: [] }],
  }
  vi.spyOn(fetchHutDetailModule, 'fetchHutDetail').mockResolvedValue(detail)

  render(
    <AvailabilityDetailPanel
      chain={chain} hutNameById={hutNameById} hutOhrsByIndex={hutOhrsByIndex}
      startDate={new Date(Date.UTC(2026, 7, 20))} numOfPeople={2}
    />,
  )

  await waitFor(() => expect(screen.getByText('Hütte geschlossen (Saison)')).toBeInTheDocument())
})

it('renders nothing for a hut with no ohrsHutId (direct-booking-only)', () => {
  render(
    <AvailabilityDetailPanel
      chain={chain} hutNameById={hutNameById} hutOhrsByIndex={new Map([[0, { ohrsHutId: null, tenantCode: null }]])}
      startDate={new Date(Date.UTC(2026, 7, 20))} numOfPeople={2}
    />,
  )
  expect(screen.queryByText('Pfeis-Hütte')).not.toBeInTheDocument()
})
