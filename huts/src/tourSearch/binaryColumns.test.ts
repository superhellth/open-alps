import { describe, it, expect } from 'vitest'
import { readColumns, packColumns } from './binaryColumns.js'
import type { Dtype } from './binaryColumns.js'

describe('binaryColumns', () => {
  it('reads columns at their declared byte offsets', () => {
    // 3 rows: id (u1) then val (f4), laid out per-column like the real payload.
    const buffer = new ArrayBuffer(3 * 1 + 3 * 4)
    const view = new DataView(buffer)
    view.setUint8(0, 7); view.setUint8(1, 8); view.setUint8(2, 9)
    view.setFloat32(3, 1.5, true); view.setFloat32(7, 2.5, true); view.setFloat32(11, 3.5, true)
    const manifest = { rows: 3, columns: { id: { dtype: 'u1' as Dtype, offset: 0 }, val: { dtype: 'f4' as Dtype, offset: 3 } } }

    const columns = readColumns(buffer, manifest)

    expect(columns.id).toEqual([7, 8, 9])
    expect(columns.val[0]).toBeCloseTo(1.5, 5)
    expect(columns.val[2]).toBeCloseTo(3.5, 5)
  })

  it('reads u8 as a safe Number, not a BigInt', () => {
    const buffer = new ArrayBuffer(8)
    new DataView(buffer).setBigUint64(0, 2986313292n, true)
    const columns = readColumns(buffer, { rows: 1, columns: { startId: { dtype: 'u8' as Dtype, offset: 0 } } })
    expect(columns.startId).toEqual([2986313292])
    expect(typeof columns.startId[0]).toBe('number')
  })

  it('throws on an unsupported dtype rather than silently misreading', () => {
    expect(() => readColumns(new ArrayBuffer(4), { rows: 1, columns: { x: { dtype: 'f8' as Dtype, offset: 0 } } }))
      .toThrow(/unsupported dtype/)
  })

  it('packColumns then readColumns round-trips', () => {
    const { manifest, buffer } = packColumns(
      { a: 'u2', b: 'f4' },
      { a: [10, 20, 30], b: [1.25, -2.5, 0] },
      3,
    )
    const columns = readColumns(buffer, manifest)
    expect(columns.a).toEqual([10, 20, 30])
    expect(columns.b[0]).toBeCloseTo(1.25, 5)
    expect(columns.b[1]).toBeCloseTo(-2.5, 5)
  })
})
