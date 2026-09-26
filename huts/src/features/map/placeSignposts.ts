import type { Heading, TourAnchor } from '@/tourSearch/tourAnchor.js'
import type { TourBoardLabel } from './tourBoard.js'

export type Side = 'left' | 'right'
export interface Pixel { x: number; y: number }
export interface Viewport { width: number; height: number }

export interface PlaceTour { key: string; label: TourBoardLabel; candidates: TourAnchor[] }
export interface Placement { key: string; kind: 'board' | 'dot'; lat: number; lng: number; side: Side }

/** Board height and mast height in px (`--board-h`, `--mast-h` in map.css). */
const BOARD_H = 26
const MAST_H = 24
/** Widest a board can be (`max-width` in map.css). */
const BOARD_MAX_W = 220
/** Horizontal padding, gap between time and ascent (map.css `.sign`). */
const PAD_LEFT = 8
const PAD_RIGHT = 16
const GAP = 6
/** Round-trip loop icon width (map.css `.loop svg`). */
const LOOP_W = 14
/** Free space kept around every placed board. */
const BOX_MARGIN = 4
/** A dot keeps this far from every board foot and earlier dot. */
const DOT_CLEARANCE = 8

const BOARD_FONT = "600 0.8rem 'Barlow Semi Condensed', 'Barlow', sans-serif"

/** Board width from its texts and loop icon, clamped to the CSS `max-width`. */
export function boardWidth(label: TourBoardLabel, textWidth: (text: string) => number): number {
  const loop = label.roundTrip ? LOOP_W + GAP : 0
  return Math.min(BOARD_MAX_W, PAD_LEFT + loop + textWidth(label.text) + GAP + textWidth(label.detail) + PAD_RIGHT)
}

let canvasContext: CanvasRenderingContext2D | null | undefined

function canvasTextWidth(text: string): number {
  if (canvasContext === undefined) {
    canvasContext = document.createElement('canvas').getContext('2d')
    if (canvasContext) canvasContext.font = BOARD_FONT
  }
  return canvasContext ? canvasContext.measureText(text).width : text.length * 7
}

/** Width of a tour's board in px, measured in the board font. */
export function measureBoard(label: TourBoardLabel): number {
  return boardWidth(label, canvasTextWidth)
}

interface Box { left: number; top: number; right: number; bottom: number }

/** The board and its mast on foot `foot`. An east board's tail edge sits on the mast's outer edge and extends right; a west board mirrors it. */
function boxOf(foot: Pixel, side: Side, width: number): Box {
  const top = foot.y - MAST_H - BOARD_H
  return side === 'right'
    ? { left: foot.x - 1, right: foot.x - 1 + width, top, bottom: foot.y }
    : { left: foot.x + 1 - width, right: foot.x + 1, top, bottom: foot.y }
}

const overlaps = (a: Box, b: Box, gap: number) =>
  a.left - gap < b.right && a.right + gap > b.left && a.top - gap < b.bottom && a.bottom + gap > b.top

const inside = (b: Box, v: Viewport) => b.left >= 0 && b.top >= 0 && b.right <= v.width && b.bottom <= v.height
const footInside = (f: Pixel, v: Viewport) => f.x >= 0 && f.y >= 0 && f.x <= v.width && f.y <= v.height

const sideOf = (heading: Heading): Side => (heading === 'west' ? 'left' : 'right')
const opposite = (side: Side): Side => (side === 'left' ? 'right' : 'left')

/** The tour's candidates with its previous spot, when still a candidate, moved to the front. */
function previousFirst(candidates: TourAnchor[], prev: Placement | undefined): TourAnchor[] {
  const i = prev ? candidates.findIndex((c) => c.lat === prev.lat && c.lng === prev.lng) : -1
  return i <= 0 ? candidates : [candidates[i], ...candidates.slice(0, i), ...candidates.slice(i + 1)]
}

/** Greedy signpost placement in rank order (`tours`, best first), sticky to `previous` (the last placement).
 *  A board whose foot is still on one of its tour's candidates and in the viewport is pinned: it never moves or turns. Pinned
 *  boards go first, in rank order; each stays where it was when clear of every board placed so far (it may overhang the
 *  viewport), else becomes a dot on that spot. Every other tour, in rank order, takes the first candidate and side whose box
 *  lies in the viewport and clear of every board so far (its previous dot spot first, heading side first). A tour with no
 *  such box becomes a dot after all boards, at the first candidate clear of every foot (previous spot first), else at its
 *  first candidate. Result: boards then dots, each in placement order. */
export function placeSignposts(
  tours: PlaceTour[],
  project: (p: { lat: number; lng: number }) => Pixel,
  measure: (label: TourBoardLabel) => number,
  viewport: Viewport,
  previous: readonly Placement[] = [],
): Placement[] {
  const prevByKey = new Map(previous.map((p) => [p.key, p]))
  const boxes: Box[] = []
  const feet: Pixel[] = []
  const boards: Placement[] = []
  const dots: Placement[] = []
  const unplaced: PlaceTour[] = []

  const tryBoard = (tour: PlaceTour, c: TourAnchor, foot: Pixel, side: Side, box: Box): boolean => {
    if (boxes.some((b) => overlaps(box, b, BOX_MARGIN))) return false
    boxes.push(box)
    feet.push(foot)
    boards.push({ key: tour.key, kind: 'board', lat: c.lat, lng: c.lng, side })
    return true
  }

  const board = (tour: PlaceTour, width: number): boolean => {
    for (const c of previousFirst(tour.candidates, prevByKey.get(tour.key))) {
      const foot = project(c)
      const preferred = sideOf(c.heading)
      for (const side of [preferred, opposite(preferred)]) {
        const box = boxOf(foot, side, width)
        if (inside(box, viewport) && tryBoard(tour, c, foot, side, box)) return true
      }
    }
    return false
  }

  const pinnedSpot = (tour: PlaceTour) => {
    const prev = prevByKey.get(tour.key)
    if (prev?.kind !== 'board') return null
    const c = tour.candidates.find((a) => a.lat === prev.lat && a.lng === prev.lng)
    const foot = c && project(c)
    return c && foot && footInside(foot, viewport) ? { c, foot, side: prev.side } : null
  }

  const free: PlaceTour[] = []
  for (const tour of tours) {
    const pin = pinnedSpot(tour)
    if (!pin) { free.push(tour); continue }
    if (tryBoard(tour, pin.c, pin.foot, pin.side, boxOf(pin.foot, pin.side, measure(tour.label)))) continue
    feet.push(pin.foot)
    dots.push({ key: tour.key, kind: 'dot', lat: pin.c.lat, lng: pin.c.lng, side: sideOf(pin.c.heading) })
  }

  for (const tour of free) {
    if (tour.candidates.length === 0) continue
    if (!board(tour, measure(tour.label))) unplaced.push(tour)
  }

  for (const tour of unplaced) {
    const spots = previousFirst(tour.candidates, prevByKey.get(tour.key)).map((c) => ({ c, foot: project(c) }))
    const spot = spots.find(({ foot }) => !feet.some((f) => Math.hypot(f.x - foot.x, f.y - foot.y) < DOT_CLEARANCE)) ?? spots[0]
    feet.push(spot.foot)
    dots.push({ key: tour.key, kind: 'dot', lat: spot.c.lat, lng: spot.c.lng, side: sideOf(spot.c.heading) })
  }

  return [...boards, ...dots]
}
