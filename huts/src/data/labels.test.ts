import { describe, it, expect } from 'vitest'
import { idFromOsmFeatureId, makeStartLabel } from './labels.js'
import type { StartPoint } from './types.js'

describe('idFromOsmFeatureId', () => {
  it('strips the OSM prefix and rejects non-ids', () => {
    expect(idFromOsmFeatureId('n123')).toBe(123)
    expect(idFromOsmFeatureId('x')).toBeNull()
  })
})

describe('makeStartLabel', () => {
  const start = (name: string | null, sourceType: number): StartPoint => ({ name, sourceType, lat: 0, lng: 0 })
  const label = makeStartLabel(new Map([
    [1, start('Innsbruck Hbf', 1)], [2, start('Talort', 2)], [3, start(null, 2)],
  ]))
  it('uses the bare name for stations and adds the kind for other points', () => {
    expect(label(1)).toBe('Innsbruck Hbf')
    expect(label(2)).toBe('Talort (Parkplatz)')
    expect(label(3)).toBe('Parkplatz')
    expect(label(7)).toBe('Startpunkt 7')
  })
})
