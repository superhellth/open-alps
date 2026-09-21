import { describe, it, expect } from 'vitest'
import { groupByStart } from './groupByStart.js'

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
