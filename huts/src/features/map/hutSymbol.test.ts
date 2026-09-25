import { describe, it, expect } from 'vitest'
import { hutSymbolSvg, startSymbolSvg } from './hutSymbol.js'

describe('hutSymbolSvg', () => {
  it('uses a house polygon for every hut', () => {
    expect(hutSymbolSvg({ serviced: true })).toContain('<polygon')
  })
  it('serviced = ink fill, self-catering = ink outline on paper', () => {
    expect(hutSymbolSvg({ serviced: true })).toContain('fill="#23272B"')
    const outline = hutSymbolSvg({ serviced: false })
    expect(outline).toContain('fill="#EDEFE9"')
    expect(outline).toContain('stroke="#23272B"')
  })
  it('a selected hut is a house, signpost-yellow fill, ink outline', () => {
    const s = hutSymbolSvg({ serviced: false, selected: true })
    expect(s).toContain('<polygon')
    expect(s).toContain('fill="#F5B700"')
    expect(s).toContain('stroke="#23272B"')
  })
})

describe('startSymbolSvg', () => {
  it('draws distinct symbols for station, parking and village', () => {
    const [station, parking, village] = [1, 2, 3].map((t) => startSymbolSvg(t))
    expect(new Set([station, parking, village]).size).toBe(3)
    expect(parking).toContain('>P<')
    expect(station).toContain('<path')
  })
})
