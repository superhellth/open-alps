// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { GPX_NS, deleteEdit, insertEdit, listPoints, mergeGpx, moveEdit, parseGpx, serializeGpx, splitGpx } from './gpxDoc.js'

const SRC =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
  `<gpx version="1.1" xmlns="${GPX_NS}" xmlns:oa="http://www.outdooractive.com/GPX/Extensions/1">\n` +
  '  <trk>\n    <trkseg>\n' +
  '      <trkpt lat="47.100000" lon="11.100000">\n        <ele>1000.0</ele>\n      </trkpt>\n' +
  '      <trkpt lat="47.200000" lon="11.200000">\n        <ele>1100.0</ele>\n        <extensions><oa:x>1</oa:x></extensions>\n      </trkpt>\n' +
  '      <trkpt lat="47.300000" lon="11.300000">\n        <ele>1200.0</ele>\n      </trkpt>\n' +
  '    </trkseg>\n  </trk>\n</gpx>\n'

describe('gpxDoc', () => {
  it('serializes an untouched document identically (prolog, epilog, extensions)', () => {
    expect(serializeGpx(parseGpx(SRC))).toBe(SRC)
  })

  it('lists points as lon/lat', () => {
    expect(listPoints(parseGpx(SRC))[1]).toEqual({ lon: 11.2, lat: 47.2 })
  })

  it('rejects malformed xml', () => {
    expect(() => parseGpx('<gpx><trk></gpx>')).toThrow()
  })

  it('move writes 6 decimals, changes only that point, and reverts exactly', () => {
    const g = parseGpx(SRC)
    const e = moveEdit(g, 1, { lon: 11.25, lat: 47.25 })
    e.apply()
    const out = serializeGpx(g)
    expect(out).toContain('<trkpt lat="47.250000" lon="11.250000">')
    expect(out.replace('47.250000', '47.200000').replace('11.250000', '11.200000')).toBe(SRC)
    e.revert()
    expect(serializeGpx(g)).toBe(SRC)
  })

  it('insert creates GPX-namespace trkpt without ele/xmlns="" and keeps line layout', () => {
    const g = parseGpx(SRC)
    const e = insertEdit(g, 0, [{ lon: 11.15, lat: 47.15 }])
    e.apply()
    const out = serializeGpx(g)
    expect(out).toContain(
      '</trkpt>\n      <trkpt lat="47.150000" lon="11.150000"/>\n      <trkpt lat="47.200000"',
    )
    expect(out).not.toContain('xmlns=""')
    const created = g.doc.getElementsByTagNameNS(GPX_NS, 'trkpt')[1]!
    expect(created.namespaceURI).toBe(GPX_NS)
    expect(created.children.length).toBe(0)
    expect(listPoints(g)).toHaveLength(4)
    e.revert()
    expect(serializeGpx(g)).toBe(SRC)
  })

  it('insert of several points keeps their order', () => {
    const g = parseGpx(SRC)
    insertEdit(g, 1, [{ lon: 11.21, lat: 47.21 }, { lon: 11.22, lat: 47.22 }]).apply()
    expect(listPoints(g).map((p) => p.lat)).toEqual([47.1, 47.2, 47.21, 47.22, 47.3])
  })

  it('delete removes the point and its indent; revert restores exactly', () => {
    const g = parseGpx(SRC)
    const e = deleteEdit(g, 1)
    e.apply()
    expect(listPoints(g).map((p) => p.lat)).toEqual([47.1, 47.3])
    expect(serializeGpx(g)).not.toContain('oa:x')
    e.revert()
    expect(serializeGpx(g)).toBe(SRC)
  })

  it('redo after undo of delete works', () => {
    const g = parseGpx(SRC)
    const e = deleteEdit(g, 0)
    e.apply()
    e.revert()
    e.apply()
    expect(listPoints(g)).toHaveLength(2)
  })
})

describe('splitGpx / mergeGpx', () => {
  it('split shares the split point and keeps the prolog', () => {
    const [head, tail] = splitGpx(SRC, 1)
    expect(listPoints(parseGpx(head))).toEqual([{ lon: 11.1, lat: 47.1 }, { lon: 11.2, lat: 47.2 }])
    expect(listPoints(parseGpx(tail))).toEqual([{ lon: 11.2, lat: 47.2 }, { lon: 11.3, lat: 47.3 }])
    expect(head.startsWith('<?xml')).toBe(true)
    expect(tail).toContain('<oa:x>1</oa:x>')
  })

  it('split rejects endpoints and out-of-range indices', () => {
    expect(() => splitGpx(SRC, 0)).toThrow()
    expect(() => splitGpx(SRC, 2)).toThrow()
  })

  it('merge undoes a split byte-for-byte on points', () => {
    const [head, tail] = splitGpx(SRC, 1)
    expect(listPoints(parseGpx(mergeGpx(head, tail)))).toEqual(listPoints(parseGpx(SRC)))
  })

  it('merge keeps distinct join points and puts new points in the GPX namespace', () => {
    const [head, tail] = splitGpx(SRC, 1)
    const merged = parseGpx(mergeGpx(head, splitGpx(SRC, 1)[1].replace('47.200000', '47.250000')))
    expect(listPoints(merged)).toHaveLength(4)
    expect(merged.doc.getElementsByTagNameNS(GPX_NS, 'trkpt')).toHaveLength(4)
    expect(tail).toBeTruthy()
  })
})
