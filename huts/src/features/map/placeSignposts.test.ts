// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest'
import { boardWidth, measureBoard, placeSignposts } from './placeSignposts.js'
import type { PlaceTour, Placement } from './placeSignposts.js'
import type { TourAnchor } from '@/tourSearch/tourAnchor.js'
import type { TourBoardLabel } from './tourBoard.js'

const label = (text = 'x'): TourBoardLabel => ({ text, detail: '↑ 1 m', roundTrip: false, title: text })
/** Identity-like projection: lng is x, lat is y in pixels. */
const project = (p: { lat: number; lng: number }) => ({ x: p.lng, y: p.lat })
const at = (x: number, y: number, heading: 'east' | 'west' = 'east'): TourAnchor => ({ lat: y, lng: x, heading })
const tour = (key: string, candidates: TourAnchor[], text = 'x'): PlaceTour => ({ key, label: label(text), candidates })
const VIEWPORT = { width: 1000, height: 1000 }
const fixed = (w: number) => (_label: TourBoardLabel) => w
// A board is 100 px wide, 26 px + 24 px mast tall: an east board on foot (x, y) covers x-1..x+99, y-50..y.

const place = (tours: PlaceTour[], measure = fixed(100)) => placeSignposts(tours, project, measure, VIEWPORT)
const byKey = (ps: ReturnType<typeof place>, key: string) => ps.find((p) => p.key === key)!

describe('placeSignposts', () => {
  it('gives a lone tour a board at its first candidate, on its heading side', () => {
    expect(place([tour('a', [at(500, 500)])])).toEqual([{ key: 'a', kind: 'board', lat: 500, lng: 500, side: 'right' }])
    expect(place([tour('a', [at(500, 500, 'west')])])[0].side).toBe('left')
  })

  it('lets the better-ranked tour win a collision; the other, with no other candidate, becomes a dot', () => {
    const ps = place([tour('a', [at(500, 500)]), tour('b', [at(500, 500)])])
    expect(byKey(ps, 'a').kind).toBe('board')
    expect(byKey(ps, 'b').kind).toBe('dot')
  })

  it('moves a lower-ranked tour to its next candidate', () => {
    const ps = place([tour('a', [at(500, 500)]), tour('b', [at(500, 500), at(500, 700)])])
    expect(byKey(ps, 'b')).toMatchObject({ kind: 'board', lat: 700, lng: 500 })
  })

  it('gives tours with an identical candidate list boards on different candidates', () => {
    const list = [at(500, 500), at(500, 700)]
    const ps = place([tour('a', list), tour('b', list)])
    expect(byKey(ps, 'a')).toMatchObject({ kind: 'board', lat: 500 })
    expect(byKey(ps, 'b')).toMatchObject({ kind: 'board', lat: 700 })
  })

  it('uses the other side when the heading side collides', () => {
    // a covers x 499..599. b heading west from x 650 would cover 551..651 (collides); the east side covers 649..749.
    const ps = place([tour('a', [at(500, 500)]), tour('b', [at(650, 500, 'west')])])
    expect(byKey(ps, 'b')).toMatchObject({ kind: 'board', side: 'right' })
  })

  it('uses the other side when the heading side leaves the viewport', () => {
    expect(place([tour('a', [at(950, 500, 'east')])])[0]).toMatchObject({ kind: 'board', side: 'left' })
    expect(place([tour('a', [at(50, 500, 'west')])])[0]).toMatchObject({ kind: 'board', side: 'right' })
  })

  it('makes a dot when neither side fits the viewport, here at the top edge', () => {
    expect(place([tour('a', [at(500, 20)])])[0].kind).toBe('dot')
  })

  it('keeps a 4 px margin between boards', () => {
    // a covers x 499..599; b east from x 602 starts at 601 (2 px gap): too close, west side too; so b is a dot.
    const ps = place([tour('a', [at(500, 500)]), tour('b', [at(602, 500)])])
    expect(byKey(ps, 'b').kind).toBe('dot')
    const clear = place([tour('a', [at(500, 500)]), tour('b', [at(605, 500)])])
    expect(byKey(clear, 'b').kind).toBe('board')
  })

  it('lists boards first, then dots, each in rank order; dots never block boards', () => {
    const measure = (l: TourBoardLabel) => (l.text === 'wide' ? 2000 : 100)
    const ps = place([tour('dotFirst', [at(500, 500)], 'wide'), tour('b', [at(500, 500)]), tour('c', [at(500, 800)])], measure)
    expect(ps.map((p) => `${p.key}:${p.kind}`)).toEqual(['b:board', 'c:board', 'dotFirst:dot'])
  })

  it('skips a tour without candidates', () => {
    expect(place([tour('a', [])])).toEqual([])
  })

  describe('dots', () => {
    const wide = fixed(2000) // no board fits, every tour is a dot
    const p1 = at(100, 100)
    const p2 = at(300, 100)

    it('avoid the feet of earlier dots by taking a later candidate', () => {
      const ps = place([tour('a', [p1, p2]), tour('b', [p1, p2])], wide)
      expect(byKey(ps, 'a')).toMatchObject({ kind: 'dot', lng: 100 })
      expect(byKey(ps, 'b')).toMatchObject({ kind: 'dot', lng: 300 })
    })

    it('treat a foot within 8 px as taken and one at 8 px as free', () => {
      const near = place([tour('a', [p1]), tour('b', [at(107, 100), p2])], wide)
      expect(byKey(near, 'b').lng).toBe(300)
      const free = place([tour('a', [p1]), tour('b', [at(108, 100), p2])], wide)
      expect(byKey(free, 'b').lng).toBe(108)
    })

    it('fall back to their first candidate when every candidate is taken', () => {
      const ps = place([tour('a', [p1]), tour('b', [p1])], wide)
      expect(byKey(ps, 'b')).toMatchObject({ kind: 'dot', lng: 100 })
    })

    it('avoid the feet of boards', () => {
      const ps = placeSignposts(
        [tour('a', [at(500, 500)]), tour('b', [at(500, 500), at(700, 700)])],
        project, (l) => (l.text === 'x' ? 100 : 2000), VIEWPORT,
      )
      expect(byKey(ps, 'b').kind).toBe('board')
      const dots = placeSignposts(
        [tour('a', [at(500, 500)]), tour('b', [at(500, 500), at(700, 700)], 'wide')],
        project, (l) => (l.text === 'x' ? 100 : 2000), VIEWPORT,
      )
      expect(byKey(dots, 'b')).toMatchObject({ kind: 'dot', lng: 700 })
    })

    it('carry the heading side of their candidate', () => {
      expect(place([tour('a', [at(100, 100, 'west')])], wide)[0].side).toBe('left')
    })
  })
})

describe('placeSignposts with a previous placement', () => {
  const again = (tours: PlaceTour[], previous: Placement[], measure = fixed(100)) =>
    placeSignposts(tours, project, measure, VIEWPORT, previous)
  const board = (key: string, x: number, y: number, side: 'left' | 'right' = 'right'): Placement =>
    ({ key, kind: 'board', lat: y, lng: x, side })

  it('keeps a board on its previous candidate and side while it still fits', () => {
    // Fresh, a would take 500,500 east; it stood at 500,700 west before.
    const ps = again([tour('a', [at(500, 500), at(500, 700)])], [board('a', 500, 700, 'left')])
    expect(ps).toEqual([board('a', 500, 700, 'left')])
  })

  it('places previous boards before better-ranked newcomers', () => {
    const ps = again([tour('new', [at(500, 500)]), tour('old', [at(500, 500)])], [board('old', 500, 500)])
    expect(byKey(ps, 'old').kind).toBe('board')
    expect(byKey(ps, 'new').kind).toBe('dot')
  })

  it('keeps a previous board whose box overhangs the viewport while its foot is in view', () => {
    // East from x 950 overhangs the right edge; fresh placement would flip it to the west side.
    expect(again([tour('a', [at(950, 500)])], [board('a', 950, 500)])[0]).toEqual(board('a', 950, 500))
  })

  it('moves a previous board whose foot left the viewport, or whose candidate is gone', () => {
    const out = again([tour('a', [at(500, 500), at(1200, 500)])], [board('a', 1200, 500)])
    expect(out[0]).toMatchObject({ kind: 'board', lng: 500 })
    const gone = again([tour('a', [at(500, 500)])], [board('a', 300, 300)])
    expect(gone[0]).toMatchObject({ kind: 'board', lng: 500 })
  })

  it('turns a pinned board that collides with an earlier pinned board into a dot on its spot', () => {
    // b could move to 500,800 but is pinned at 520,500, where a's board now covers it.
    const ps = again(
      [tour('a', [at(500, 500)]), tour('b', [at(520, 500), at(500, 800)])],
      [board('a', 500, 500), board('b', 520, 500)],
    )
    expect(byKey(ps, 'a')).toEqual(board('a', 500, 500))
    expect(byKey(ps, 'b')).toMatchObject({ kind: 'dot', lat: 500, lng: 520 })
  })

  it('never flips a pinned board to its other side', () => {
    // a's west board overlaps b's pinned east board; a's east side would be clear, but a is pinned west.
    const ps = again(
      [tour('b', [at(400, 500)]), tour('a', [at(550, 500, 'east')])],
      [board('b', 400, 500), board('a', 550, 500, 'left')],
    )
    expect(byKey(ps, 'a')).toMatchObject({ kind: 'dot', lng: 550 })
  })

  it('never lets an overhanging board take a new spot', () => {
    expect(again([tour('a', [at(950, 500)])], [board('a', 500, 500)])[0].side).toBe('left')
  })

  it('keeps a dot on its previous candidate while it is clear', () => {
    const wide = fixed(2000)
    const prev: Placement = { key: 'a', kind: 'dot', lat: 100, lng: 300, side: 'right' }
    expect(again([tour('a', [at(100, 100), at(300, 100)])], [prev], wide)[0]).toMatchObject({ kind: 'dot', lng: 300 })
  })

  it('tries a previous dot spot first when the tour now fits a board', () => {
    const prev: Placement = { key: 'a', kind: 'dot', lat: 700, lng: 500, side: 'right' }
    expect(again([tour('a', [at(500, 500), at(500, 700)])], [prev])[0]).toEqual(board('a', 500, 700))
  })
})

describe('boardWidth', () => {
  const ten = (s: string) => s.length * 10
  it('adds padding, gap and both texts', () => {
    // 8 left padding + 'ab' (20) + 6 gap + '↑ 1m' (40) + 16 right padding
    expect(boardWidth({ text: 'ab', detail: '↑ 1m', roundTrip: false, title: '' }, ten)).toBe(90)
  })
  it('clamps a long text to 220 px', () => {
    expect(boardWidth({ text: 'x'.repeat(200), detail: '↑ 1 m', roundTrip: false, title: '' }, ten)).toBe(220)
  })
  it('adds the loop icon and its gap for a round trip', () => {
    expect(boardWidth({ text: 'ab', detail: '↑ 1m', roundTrip: true, title: '' }, ten)).toBe(110)
  })
})

describe('measureBoard', () => {
  it('falls back to an estimate when canvas is unavailable', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    const width = measureBoard(label('Kaunertal'))
    expect(width).toBeGreaterThan(30)
    expect(width).toBeLessThanOrEqual(220)
    vi.restoreAllMocks()
  })
})
