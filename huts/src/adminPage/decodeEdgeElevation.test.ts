import { describe, it, expect } from 'vitest'
import { decodeEdgeElevation } from './decodeEdgeElevation.js'

describe('decodeEdgeElevation', () => {
  it('slices the flat f4 buffer per edge using profile_counts as prefix-sum offsets', () => {
    const values = new Float32Array([100.5, 101.5, 200.5, 201.5, 202.5])
    const perEdge = decodeEdgeElevation({ profile_counts: [2, 3] }, values.buffer)

    expect(perEdge).toHaveLength(2)
    expect(perEdge[0]).toEqual([100.5, 101.5])
    expect(perEdge[1]).toEqual([200.5, 201.5, 202.5])
  })

  it('yields an empty array for a degenerate edge with profile_count 0', () => {
    const values = new Float32Array([50, 51])
    const perEdge = decodeEdgeElevation({ profile_counts: [0, 2] }, values.buffer)

    expect(perEdge[0]).toEqual([])
    expect(perEdge[1]).toEqual([50, 51])
  })

  it('handles an empty manifest', () => {
    const perEdge = decodeEdgeElevation({ profile_counts: [] }, new ArrayBuffer(0))
    expect(perEdge).toEqual([])
  })
})
