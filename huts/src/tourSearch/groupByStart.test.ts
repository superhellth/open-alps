import { describe, it, expect } from 'vitest'
import { bestStartId, groupByStart } from './groupByStart.js'

describe('groupByStart', () => {
  it('groups by startId in first-appearance order, keeping tour order inside a group', () => {
    const tours = [{ startId: 2, n: 'a' }, { startId: 1, n: 'b' }, { startId: 2, n: 'c' }]
    expect(groupByStart(tours)).toEqual([
      { startId: 2, tours: [tours[0], tours[2]] },
      { startId: 1, tours: [tours[1]] },
    ])
  })
  it('returns no groups for no tours', () => {
    expect(groupByStart([])).toEqual([])
  })
})

describe('bestStartId', () => {
  it('picks the start with the most tours', () => {
    const groups = [{ startId: 1, tours: [{}] }, { startId: 2, tours: [{}, {}, {}] }, { startId: 3, tours: [{}, {}] }]
    expect(bestStartId(groups)).toBe(2)
  })
  it('breaks ties by the lowest startId', () => {
    const groups = [{ startId: 5, tours: [{}, {}] }, { startId: 2, tours: [{}, {}] }]
    expect(bestStartId(groups)).toBe(2)
  })
  it('is null for an empty list', () => {
    expect(bestStartId([])).toBeNull()
  })
})
