// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { SPREAD_CAP, clusterHtml, escapeHtml, singleHtml, stackHtml } from './signpostHtml.js'
import type { BoardTour } from './signpostHtml.js'

const bt = (i: number, text = `Ziel ${i}`): BoardTour => ({
  key: `k${i}`, label: { text, distance: `${i}.0 km`, title: `Ziel ${i} (Parkplatz), ${i}.0 km`, sourceType: 2 },
})
const doc = (html: string) => { const d = document.createElement('div'); d.innerHTML = html; return d }

describe('singleHtml', () => {
  it('is one focusable board with the tour key, end point, distance and title', () => {
    const d = doc(singleHtml(bt(1)))
    const sign = d.querySelector('.sign[data-tour-key="k1"]')!
    expect(sign.getAttribute('tabindex')).toBe('0')
    expect(sign.getAttribute('title')).toBe('Ziel 1 (Parkplatz), 1.0 km')
    expect(sign.textContent).toContain('Ziel 1')
    expect(sign.textContent).toContain('1.0 km')
    expect(sign.querySelector('svg')).not.toBeNull()
  })
  it('escapes the end point name', () => {
    expect(singleHtml(bt(1, '<b>&"'))).not.toContain('<b>')
    expect(escapeHtml('<&>"')).toBe('&lt;&amp;&gt;&quot;')
  })
})

describe('stackHtml', () => {
  it('has a body sign with the tour count, a backdrop and one board per tour', () => {
    const d = doc(stackHtml([bt(1), bt(2), bt(3)]))
    expect(d.querySelector('.sign')!.textContent).toBe('3')
    expect(d.querySelector('.spread-backdrop')).not.toBeNull()
    expect([...d.querySelectorAll('.board[data-tour-key]')].map((b) => b.getAttribute('data-tour-key'))).toEqual(['k1', 'k2', 'k3'])
    expect(d.querySelector('[data-overflow]')).toBeNull()
  })
  it('stacks boards on the pole in list order, first at the top', () => {
    const ups = [...doc(stackHtml([bt(1), bt(2), bt(3)])).querySelectorAll<HTMLElement>('.board')].map((b) => b.style.getPropertyValue('--up'))
    expect(ups).toEqual(['3', '2', '1'])
  })
  it('caps the spread and adds an overflow board with a title naming the total', () => {
    const tours = Array.from({ length: SPREAD_CAP + 4 }, (_, i) => bt(i))
    const d = doc(stackHtml(tours))
    expect(d.querySelectorAll('.board[data-tour-key]')).toHaveLength(SPREAD_CAP)
    const overflow = d.querySelector('.board.overflow[data-overflow]')!
    expect(overflow.textContent).toBe('+4')
    expect(overflow.getAttribute('title')).toBe('Alle 12 Touren in der Liste zeigen')
  })
  it('adds no overflow board at exactly the cap', () => {
    const d = doc(stackHtml(Array.from({ length: SPREAD_CAP }, (_, i) => bt(i))))
    expect(d.querySelector('[data-overflow]')).toBeNull()
  })
})

describe('clusterHtml', () => {
  it('is a two-arm sign with the summed count', () => {
    const d = doc(clusterHtml(214))
    expect(d.querySelector('.sign.cluster-sign')!.textContent).toBe('214')
    expect(d.querySelectorAll('.arm')).toHaveLength(2)
  })
})
