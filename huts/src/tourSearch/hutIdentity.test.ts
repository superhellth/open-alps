import { describe, it, expect } from 'vitest'
import { resolveHutGuids, hutGuidsForIndices } from './hutIdentity.js'

describe('hut identity', () => {
  it('resolves saved GUIDs after the payload order changed', () => {
    const saved = hutGuidsForIndices(['{A}', '{B}', '{C}'], [2, 0])
    expect(resolveHutGuids(['{C}', '{A}', '{B}'], saved)).toEqual([0, 1])
  })

  it('resolves a GUID no longer in the payload to null', () => {
    expect(resolveHutGuids(['{A}'], ['{A}', '{GONE}'])).toEqual([0, null])
  })
})
