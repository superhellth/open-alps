export interface Pt {
  x: number
  y: number
}

export interface Rect {
  minX: number
  minY: number
  maxX: number
  maxY: number
}

const inside = (p: Pt, r: Rect) => p.x >= r.minX && p.x <= r.maxX && p.y >= r.minY && p.y <= r.maxY
const dist = (a: Pt, b: Pt) => Math.hypot(a.x - b.x, a.y - b.y)

export function chooseHandles(px: Pt[], viewport: Rect, minSpacingPx: number): number[] {
  const n = px.length
  if (n === 0) return []
  if (n === 1) return [0]
  const chosen = [0]
  let last = px[0]!
  for (let i = 1; i < n - 1; i++) {
    const p = px[i]!
    if (!inside(p, viewport) || dist(p, last) < minSpacingPx) continue
    chosen.push(i)
    last = p
  }
  if (chosen.length > 1 && dist(px[chosen[chosen.length - 1]!]!, px[n - 1]!) < minSpacingPx) chosen.pop()
  chosen.push(n - 1)
  return chosen
}
