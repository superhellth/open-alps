// @vitest-environment jsdom
import { it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import TourList from './TourList.js'
import type { SearchResult, TourResult } from '../tourSearch/types.js'
import type { HutClass } from '../hutClass.js'

const chain: TourResult = {
  huts: [0], startId: 100, exitStartId: 100,
  totalDurationH: 5, totalAscentM: 500, totalDescentM: 500, totalDistanceM: 8000,
  legs: [
    { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 0, reversed: false },
    { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 1, reversed: true },
  ],
}
const result: SearchResult = { chains: [chain], killCounters: { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 0, trackOverlap: 0 } }
const hutNameById = new Map([[0, 'HutA']])
const hutClassByIndex = new Map<number, HutClass>([[0, { operator: 'av', serviced: false }]])

it('shows the hut class badge next to the hut name in the expanded chain sentence', () => {
  render(
    <TourList
      result={result} displayedChains={[chain]} pageChains={[chain]} page={1} pageCount={1}
      setPage={() => {}} sortKey="duration" setSortKey={() => {}} hutNameById={hutNameById}
      hutClassByIndex={hutClassByIndex} startLabel={() => 'Start'}
      expandedChain={0} setExpandedChain={() => {}} mode="transit"
    />,
  )
  expect(screen.getByText('AV·SV')).toBeInTheDocument()
})
