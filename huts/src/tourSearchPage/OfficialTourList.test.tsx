// @vitest-environment jsdom
import { it, expect, afterEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom/vitest'
import OfficialTourList from './OfficialTourList.js'
import type { OfficialTourView } from '../tourSearch/officialTours.js'
import type { HutClass } from '../hutClass.js'

afterEach(() => cleanup())

const tour: OfficialTourView = {
  tourId: 1, name: 'Welser Höhenweg',
  legs: [
    {
      legIndex: 0, from: { type: 'parking', id: 1 }, to: { type: 'hut', id: 302 }, edgeId: 0,
      reversed: false, distanceM: 6000, ascentM: 800, descentM: 100, durationH: 2, maxEleM: 1400, sacRank: 3, viaFerrata: false,
    },
    {
      legIndex: 1, from: { type: 'hut', id: 302 }, to: { type: 'station', id: 99 }, edgeId: 1,
      reversed: false, distanceM: 10000, ascentM: 1000, descentM: 800, durationH: 3, maxEleM: 2000, sacRank: 3, viaFerrata: false,
    },
  ],
  totalDistanceM: 16000, totalAscentM: 1800, totalDescentM: 900, totalDurationH: 5,
}
const hutNameById = new Map([[302, 'Wildhütte']])
const hutClassByIndex = new Map<number, HutClass>([[302, { operator: 'av', serviced: true }]])
const startLabel = (id: number) => (id === 1 ? 'Parkplatz Test' : `Bahnhof ${id}`)

it('collapsed card shows name and totals only', () => {
  render(
    <OfficialTourList tours={[tour]} hutNameById={hutNameById} hutClassByIndex={hutClassByIndex} startLabel={startLabel} selectedTourId={null} setSelectedTourId={() => {}} hoveredLegIndex={null} setHoveredLegIndex={() => {}} />,
  )
  expect(screen.getByText('Welser Höhenweg')).toBeInTheDocument()
  expect(screen.queryByText(/Etappe 1/)).not.toBeInTheDocument()
})

it('clicking a card expands it, showing 1-based stage numbers and a hut-class badge', async () => {
  let selected: number | null = null
  const { rerender } = render(
    <OfficialTourList tours={[tour]} hutNameById={hutNameById} hutClassByIndex={hutClassByIndex} startLabel={startLabel} selectedTourId={selected} setSelectedTourId={(id) => { selected = id }} hoveredLegIndex={null} setHoveredLegIndex={() => {}} />,
  )
  await userEvent.click(screen.getByText('Welser Höhenweg'))
  rerender(
    <OfficialTourList tours={[tour]} hutNameById={hutNameById} hutClassByIndex={hutClassByIndex} startLabel={startLabel} selectedTourId={selected} setSelectedTourId={() => {}} hoveredLegIndex={null} setHoveredLegIndex={() => {}} />,
  )
  expect(screen.getByText(/Etappe 1/)).toBeInTheDocument()
  expect(screen.getByText(/Etappe 2/)).toBeInTheDocument()
  expect(screen.getByText('AV')).toBeInTheDocument()
})

it('labels a mixed hut/station waypoint chain using hutNameById and startLabel respectively', async () => {
  render(
    <OfficialTourList tours={[tour]} hutNameById={hutNameById} hutClassByIndex={hutClassByIndex} startLabel={startLabel} selectedTourId={1} setSelectedTourId={() => {}} hoveredLegIndex={null} setHoveredLegIndex={() => {}} />,
  )
  expect(screen.getAllByText(/Parkplatz Test/).length).toBeGreaterThan(0)
  expect(screen.getAllByText(/Wildhütte/).length).toBeGreaterThan(0)
  expect(screen.getAllByText(/Bahnhof 99/).length).toBeGreaterThan(0)
})

it('shows the empty-state message with no gap/spinner wording when tours is empty', () => {
  render(
    <OfficialTourList tours={[]} hutNameById={hutNameById} hutClassByIndex={hutClassByIndex} startLabel={startLabel} selectedTourId={null} setSelectedTourId={() => {}} hoveredLegIndex={null} setHoveredLegIndex={() => {}} />,
  )
  expect(screen.getByText(/keine durchgehend berechneten Routen/)).toBeInTheDocument()
})

it('hovering a leg row reports its index and shows its elevation profile', async () => {
  vi.spyOn(await import('../tourSearch/loadLegElevation.js'), 'loadLegElevation').mockResolvedValue([1400, 1700, 2000])
  const setHoveredLegIndex = vi.fn()
  const { container } = render(
    <OfficialTourList
      tours={[tour]} hutNameById={hutNameById} hutClassByIndex={hutClassByIndex} startLabel={startLabel}
      selectedTourId={1} setSelectedTourId={() => {}} hoveredLegIndex={1} setHoveredLegIndex={setHoveredLegIndex}
    />,
  )
  await vi.waitFor(() => expect(container.querySelector('svg.elevation-sparkline')).not.toBeNull())

  const rows = screen.getAllByRole('row')
  // rows[0] is the header row; the hovered leg is legIndex 1, so its own row is rows[2].
  await userEvent.hover(rows[2])
  expect(setHoveredLegIndex).toHaveBeenCalledWith(1)
  await userEvent.unhover(rows[2])
  expect(setHoveredLegIndex).toHaveBeenCalledWith(null)
})

it('the collapse chevron hides and can re-show the list', async () => {
  render(
    <OfficialTourList tours={[tour]} hutNameById={hutNameById} hutClassByIndex={hutClassByIndex} startLabel={startLabel} selectedTourId={null} setSelectedTourId={() => {}} hoveredLegIndex={null} setHoveredLegIndex={() => {}} />,
  )
  await userEvent.click(screen.getByLabelText('Tourenliste minimieren'))
  expect(screen.queryByText('Welser Höhenweg')).not.toBeInTheDocument()
  await userEvent.click(screen.getByLabelText('Tourenliste einblenden'))
  expect(screen.getByText('Welser Höhenweg')).toBeInTheDocument()
})
