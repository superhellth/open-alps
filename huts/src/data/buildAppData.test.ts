import { describe, it, expect } from 'vitest'
import { buildAppData } from './buildAppData.js'
import { makeTripGraph } from '../tourSearch/tripTestGraph.js'

const fc = (features: unknown[]) => ({ type: 'FeatureCollection', features }) as GeoJSON.FeatureCollection
const point = (lng: number, lat: number) => ({ type: 'Point', coordinates: [lng, lat] })

const input = {
  graph: makeTripGraph(),
  huts: fc([
    { type: 'Feature', properties: { id: '{A}', name: 'Hütte A', hutType: 'av', serviced: true, ohrsHutId: '179', tenantCode: 8 }, geometry: point(11, 47) },
    { type: 'Feature', properties: { id: '{B}', name: 'Hütte B', hutType: 'sonstige', serviced: false }, geometry: point(11.1, 47.1) },
    { type: 'Feature', properties: { id: '{C}', name: 'Hütte C', hutType: 'weird' }, geometry: point(11.2, 47.2) },
  ]),
  stations: fc([{ type: 'Feature', id: 'n100', properties: { name: 'Bahnhof X' }, geometry: point(11, 46.9) }]),
  parking: fc([{ type: 'Feature', id: 'n200', properties: { name: 'P Tal' }, geometry: point(11.05, 46.95) }]),
  partner: fc([{ type: 'Feature', properties: { id: 11, name: 'Dorf' }, geometry: point(12, 46) }]),
  tours: [],
}

describe('buildAppData', () => {
  const data = buildAppData(input)
  it('joins huts to payload indices by GUID', () => {
    expect(data.hutNameById.get(0)).toBe('Hütte A')
    expect(data.hutNameById.has(3)).toBe(false) // {D} has no feature
    expect(data.hutCoordsById.get(1)).toEqual({ lat: 47.1, lng: 11.1 })
  })
  it('classifies huts and leaves unknown types / unmatched huts null', () => {
    expect(data.hutsByIndex[0]).toEqual({ operator: 'av', serviced: true })
    expect(data.hutsByIndex[1]).toEqual({ operator: 'sonstige', serviced: false })
    expect(data.hutsByIndex[2]).toBeNull()
    expect(data.hutClassByIndex.size).toBe(2)
  })
  it('keeps OHRS ids and tenant codes, null when absent', () => {
    expect(data.hutOhrsByIndex.get(0)).toEqual({ ohrsHutId: '179', tenantCode: 8 })
    expect(data.hutOhrsByIndex.get(1)).toEqual({ ohrsHutId: null, tenantCode: null })
  })
  it('indexes stations, parking and partner points by their numeric ids with the right source type', () => {
    expect(data.startById.get(100)).toMatchObject({ sourceType: 1, name: 'Bahnhof X', lat: 46.9, lng: 11 })
    expect(data.startById.get(200)).toMatchObject({ sourceType: 2 })
    expect(data.startById.get(11)).toMatchObject({ sourceType: 3, name: 'Dorf' })
  })
})
