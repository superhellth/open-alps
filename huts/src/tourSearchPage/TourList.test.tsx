// @vitest-environment jsdom
import { it, expect, afterEach, vi } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import TourList from './TourList.js'
import type { SearchResult, TourResult } from '../tourSearch/types.js'
import type { HutClass } from '../hutClass.js'

// vitest.config.js doesn't set `globals: true`, so @testing-library/react's automatic
// afterEach(cleanup) never registers - without this, each test's render() stacks onto the
// previous test's un-unmounted DOM (this file added a second test in the same describe scope
// once availability badges were introduced, which is what first exposed the gap).
afterEach(() => cleanup())

const chain: TourResult = {
  huts: [0], startId: 100, exitStartId: 100,
  totalDurationH: 5, totalAscentM: 500, totalDescentM: 500, totalDistanceM: 8000,
  legs: [
    { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 0, reversed: false },
    { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 1, reversed: true },
  ],
}
const result: SearchResult = { chains: [chain], killCounters: { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 0, trackOverlap: 0, availability: 0 } }
const hutNameById = new Map([[0, 'HutA']])
const hutClassByIndex = new Map<number, HutClass>([[0, { operator: 'av', serviced: false }]])

it('shows the hut class badge next to the hut name in the expanded chain sentence', () => {
  render(
    <TourList
      result={result} displayedChains={[chain]} pageChains={[chain]} page={1} pageCount={1}
      setPage={() => {}} sortKey="duration" setSortKey={() => {}} hutNameById={hutNameById}
      hutClassByIndex={hutClassByIndex} startLabel={() => 'Start'}
      expandedChain={0} setExpandedChain={() => {}} mode="transit"
      freeByOffset={null} ohrsIdByHutIndex={new Map()} hutOhrsByIndex={new Map()} startDate={null} numOfPeople={1}
      hoveredLegIndex={null} setHoveredLegIndex={() => {}}
    />,
  )
  expect(screen.getByText('AV·SV')).toBeInTheDocument()
})

const ohrsIdByHutIndex = new Map<number, string | null>([[0, '179']])

it('shows an availability badge next to the hut name when freeByOffset data is present', () => {
  const freeByOffset = new Map<number, Set<string> | 'unknown'>([[1, new Set(['179'])]])
  render(
    <TourList
      result={result} displayedChains={[chain]} pageChains={[chain]} page={1} pageCount={1}
      setPage={() => {}} sortKey="duration" setSortKey={() => {}} hutNameById={hutNameById}
      hutClassByIndex={hutClassByIndex} startLabel={() => 'Start'}
      expandedChain={0} setExpandedChain={() => {}} mode="transit"
      freeByOffset={freeByOffset} ohrsIdByHutIndex={ohrsIdByHutIndex}
      hutOhrsByIndex={new Map()} startDate={null} numOfPeople={1}
      hoveredLegIndex={null} setHoveredLegIndex={() => {}}
    />,
  )
  expect(screen.getByText('frei')).toBeInTheDocument()
})

it('hovering a leg row reports its index and shows its elevation profile', async () => {
  vi.spyOn(await import('../tourSearch/loadLegElevation.js'), 'loadLegElevation').mockResolvedValue([1500, 1600, 1550])
  const setHoveredLegIndex = vi.fn()
  const { container } = render(
    <TourList
      result={result} displayedChains={[chain]} pageChains={[chain]} page={1} pageCount={1}
      setPage={() => {}} sortKey="duration" setSortKey={() => {}} hutNameById={hutNameById}
      hutClassByIndex={hutClassByIndex} startLabel={() => 'Start'}
      expandedChain={0} setExpandedChain={() => {}} mode="transit"
      freeByOffset={null} ohrsIdByHutIndex={new Map()} hutOhrsByIndex={new Map()} startDate={null} numOfPeople={1}
      hoveredLegIndex={1} setHoveredLegIndex={setHoveredLegIndex}
    />,
  )
  await vi.waitFor(() => expect(container.querySelector('svg.elevation-sparkline')).not.toBeNull())

  const rows = screen.getAllByRole('row')
  // rows[0] is the header row; the hovered leg is legIndex 1, so its own row is rows[2].
  fireEvent.mouseEnter(rows[2])
  expect(setHoveredLegIndex).toHaveBeenCalledWith(1)
  fireEvent.mouseLeave(rows[2])
  expect(setHoveredLegIndex).toHaveBeenCalledWith(null)
})

it('shows no availability badge when freeByOffset is null (badges-off state)', () => {
  render(
    <TourList
      result={result} displayedChains={[chain]} pageChains={[chain]} page={1} pageCount={1}
      setPage={() => {}} sortKey="duration" setSortKey={() => {}} hutNameById={hutNameById}
      hutClassByIndex={hutClassByIndex} startLabel={() => 'Start'}
      expandedChain={0} setExpandedChain={() => {}} mode="transit"
      freeByOffset={null} ohrsIdByHutIndex={ohrsIdByHutIndex}
      hutOhrsByIndex={new Map()} startDate={null} numOfPeople={1}
      hoveredLegIndex={null} setHoveredLegIndex={() => {}}
    />,
  )
  expect(screen.queryByText('frei')).not.toBeInTheDocument()
})
