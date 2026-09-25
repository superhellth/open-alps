// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { dotHtml, escapeHtml, singleHtml } from './signpostHtml.js'
import type { BoardTour } from './signpostHtml.js'

const bt = (i: number, text = `Ziel ${i}`): BoardTour => ({
  key: `k${i}`, label: { text, distance: `${i}.0 km`, title: `Ziel ${i} (Parkplatz), ${i}.0 km` },
})
const doc = (html: string) => { const d = document.createElement('div'); d.innerHTML = html; return d }

describe('singleHtml', () => {
  it('is one focusable board with the tour key, end point, distance and title', () => {
    const d = doc(singleHtml(bt(1), 'right'))
    const sign = d.querySelector('.sign[data-tour-key="k1"]')!
    expect(sign.getAttribute('tabindex')).toBe('0')
    expect(sign.getAttribute('title')).toBe('Ziel 1 (Parkplatz), 1.0 km')
    expect(sign.textContent).toContain('Ziel 1')
    expect(sign.textContent).toContain('1.0 km')
  })
  it('escapes the end point name', () => {
    expect(singleHtml(bt(1, '<b>&"'), 'right')).not.toContain('<b>')
    expect(escapeHtml('<&>"')).toBe('&lt;&amp;&gt;&quot;')
  })
  it('puts the side on the board', () => {
    expect(doc(singleHtml(bt(1), 'left')).querySelector('.sign.side-left')).not.toBeNull()
    expect(doc(singleHtml(bt(1), 'right')).querySelector('.sign.side-right')).not.toBeNull()
  })
  it('plants a mast and foot dot before the board', () => {
    const d = doc(singleHtml(bt(1), 'right'))
    expect(d.querySelector('.mast')).not.toBeNull()
    expect(d.querySelector('.foot')).not.toBeNull()
    expect(d.querySelector('.mast')!.getAttribute('data-tour-key')).toBeNull()
  })
})

describe('dotHtml', () => {
  it('is one focusable dot carrying the tour key and title, without mast or foot in the flow', () => {
    const d = doc(dotHtml(bt(1), 'left'))
    const dot = d.querySelector('.dot[data-tour-key="k1"]')!
    expect(dot.getAttribute('tabindex')).toBe('0')
    expect(dot.getAttribute('title')).toBe('Ziel 1 (Parkplatz), 1.0 km')
    expect(d.querySelector(':scope > .foot')).toBeNull()
  })
  it('holds a hidden preview board on the given side, not focusable and without a tour key', () => {
    const d = doc(dotHtml(bt(1), 'left'))
    const sign = d.querySelector('.preview .sign.side-left')!
    expect(sign.textContent).toContain('Ziel 1')
    expect(sign.textContent).toContain('1.0 km')
    expect(sign.hasAttribute('tabindex')).toBe(false)
    expect(sign.hasAttribute('data-tour-key')).toBe(false)
    expect(d.querySelector('.preview')!.getAttribute('aria-hidden')).toBe('true')
    expect(d.querySelector('.preview .mast')).not.toBeNull()
  })
  it('escapes the end point name', () => {
    expect(dotHtml(bt(1, '<b>&"'), 'right')).not.toContain('<b>')
  })
})
