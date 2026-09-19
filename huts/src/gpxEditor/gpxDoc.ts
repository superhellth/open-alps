import type { Edit } from './history.js'
import type { LonLat } from './types.js'

export const GPX_NS = 'http://www.topografix.com/GPX/1/1'

export interface GpxDoc {
  doc: Document
  /** Source text before the root element (XML declaration etc.). */
  prolog: string
  /** Source text after the root's closing tag (trailing newline). */
  epilog: string
}

export function parseGpx(text: string): GpxDoc {
  const doc = new DOMParser().parseFromString(text, 'application/xml')
  if (doc.getElementsByTagName('parsererror').length > 0) throw new Error('GPX is not well-formed XML')
  const rootStart = text.search(/<gpx[\s>]/)
  const closeAt = text.lastIndexOf('</gpx>')
  return {
    doc,
    prolog: rootStart > 0 ? text.slice(0, rootStart) : '',
    epilog: closeAt >= 0 ? text.slice(closeAt + '</gpx>'.length) : '',
  }
}

function trkpts(g: GpxDoc): Element[] {
  return Array.from(g.doc.getElementsByTagNameNS(GPX_NS, 'trkpt'))
}

function need(g: GpxDoc, index: number): Element {
  const el = trkpts(g)[index]
  if (!el) throw new Error(`no trackpoint at index ${index}`)
  return el
}

export function listPoints(g: GpxDoc): LonLat[] {
  return trkpts(g).map((el) => ({
    lon: Number(el.getAttribute('lon')),
    lat: Number(el.getAttribute('lat')),
  }))
}

export function serializeGpx(g: GpxDoc): string {
  return g.prolog + new XMLSerializer().serializeToString(g.doc.documentElement) + g.epilog
}

const fmt = (v: number) => v.toFixed(6)

function precedingWhitespace(el: Node): Text | null {
  const prev = el.previousSibling
  return prev && prev.nodeType === 3 && /^\s*$/.test(prev.textContent ?? '') ? (prev as Text) : null
}

export function moveEdit(g: GpxDoc, index: number, to: LonLat): Edit {
  const el = need(g, index)
  const prevLat = el.getAttribute('lat') ?? ''
  const prevLon = el.getAttribute('lon') ?? ''
  return {
    apply() {
      el.setAttribute('lat', fmt(to.lat))
      el.setAttribute('lon', fmt(to.lon))
    },
    revert() {
      el.setAttribute('lat', prevLat)
      el.setAttribute('lon', prevLon)
    },
  }
}

export function insertEdit(g: GpxDoc, afterIndex: number, pts: LonLat[]): Edit {
  const ref = need(g, afterIndex)
  const indent = precedingWhitespace(ref)
  const nodes: Node[] = []
  for (const p of pts) {
    if (indent) nodes.push(indent.cloneNode())
    const el = g.doc.createElementNS(GPX_NS, 'trkpt')
    el.setAttribute('lat', fmt(p.lat))
    el.setAttribute('lon', fmt(p.lon))
    nodes.push(el)
  }
  return {
    apply() {
      ref.after(...nodes)
    },
    revert() {
      nodes.forEach((n) => n.parentNode?.removeChild(n))
    },
  }
}

export function deleteEdit(g: GpxDoc, index: number): Edit {
  const el = need(g, index)
  const ws = precedingWhitespace(el)
  let parent: Node | null = null
  let anchor: Node | null = null
  return {
    apply() {
      parent = el.parentNode
      anchor = el.nextSibling
      parent?.removeChild(el)
      if (ws) ws.parentNode?.removeChild(ws)
    },
    revert() {
      if (!parent) return
      parent.insertBefore(el, anchor)
      if (ws) parent.insertBefore(ws, el)
    },
  }
}

function removePoint(el: Element): void {
  precedingWhitespace(el)?.remove()
  el.remove()
}

/** Splits at trackpoint `index`; that point ends the first document and starts the second. */
export function splitGpx(text: string, index: number): [string, string] {
  const total = trkpts(parseGpx(text)).length
  if (!Number.isInteger(index) || index < 1 || index > total - 2) {
    throw new Error(`cannot split a ${total}-point leg at point ${index}`)
  }
  const head = parseGpx(text)
  trkpts(head).slice(index + 1).forEach(removePoint)
  const tail = parseGpx(text)
  trkpts(tail).slice(0, index).forEach(removePoint)
  return [serializeGpx(head), serializeGpx(tail)]
}

const samePosition = (a: Element, b: Element) =>
  fmt(Number(a.getAttribute('lat'))) === fmt(Number(b.getAttribute('lat'))) &&
  fmt(Number(a.getAttribute('lon'))) === fmt(Number(b.getAttribute('lon')))

/** Appends `second`'s trackpoints to `first`; a duplicate join point is kept once. Metadata comes from `first`. */
export function mergeGpx(first: string, second: string): string {
  const a = parseGpx(first)
  const aPts = trkpts(a)
  const last = aPts[aPts.length - 1]
  if (!last?.parentNode) throw new Error('first leg has no trackpoints')
  const bPts = trkpts(parseGpx(second))
  const rest = bPts.length > 0 && samePosition(last, bPts[0]!) ? bPts.slice(1) : bPts
  const indent = precedingWhitespace(last)
  const nodes: Node[] = []
  for (const p of rest) {
    if (indent) nodes.push(indent.cloneNode())
    nodes.push(a.doc.importNode(p, true))
  }
  last.after(...nodes)
  return serializeGpx(a)
}
