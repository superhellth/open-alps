/**
 * Parses/builds the packed-column binary layout shared by hut-edge-payload.bin and
 * approaches.bin: each column is a contiguous run of `rows` values at its own dtype and
 * byte offset, NOT interleaved (docs/tour-suggestion-payload.md §1) — that layout is what
 * the pipeline's gzip-size measurements assume, so columns must be read independently.
 */
const DTYPES = {
  u1: { bytes: 1, get: (v, o) => v.getUint8(o), set: (v, o, x) => v.setUint8(o, x) },
  i1: { bytes: 1, get: (v, o) => v.getInt8(o), set: (v, o, x) => v.setInt8(o, x) },
  u2: { bytes: 2, get: (v, o) => v.getUint16(o, true), set: (v, o, x) => v.setUint16(o, x, true) },
  u4: { bytes: 4, get: (v, o) => v.getUint32(o, true), set: (v, o, x) => v.setUint32(o, x, true) },
  u8: { bytes: 8, get: (v, o) => Number(v.getBigUint64(o, true)), set: (v, o, x) => v.setBigUint64(o, BigInt(x), true) },
  f4: { bytes: 4, get: (v, o) => v.getFloat32(o, true), set: (v, o, x) => v.setFloat32(o, x, true) },
}

export function readColumns(buffer, manifest) {
  const view = new DataView(buffer)
  const out = {}
  for (const [name, { dtype, offset }] of Object.entries(manifest.columns)) {
    const dt = DTYPES[dtype]
    if (!dt) throw new Error(`unsupported dtype "${dtype}" for column "${name}"`)
    const values = new Array(manifest.rows)
    for (let i = 0; i < manifest.rows; i++) values[i] = dt.get(view, offset + i * dt.bytes)
    out[name] = values
  }
  return out
}

export function packColumns(columnDefs, columnValues, rows) {
  let offset = 0
  const manifest = { rows, columns: {} }
  for (const [name, dtype] of Object.entries(columnDefs)) {
    manifest.columns[name] = { dtype, offset }
    offset += DTYPES[dtype].bytes * rows
  }
  const buffer = new ArrayBuffer(offset)
  const view = new DataView(buffer)
  for (const [name, dtype] of Object.entries(columnDefs)) {
    const dt = DTYPES[dtype]
    const colOffset = manifest.columns[name].offset
    const values = columnValues[name]
    for (let i = 0; i < rows; i++) dt.set(view, colOffset + i * dt.bytes, values[i])
  }
  return { manifest, buffer }
}
