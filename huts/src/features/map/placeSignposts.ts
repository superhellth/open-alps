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
/** Horizontal padding, gap between name and distance (map.css `.sign`). */
const PAD_LEFT = 8
const PAD_RIGHT = 16
const GAP = 6
/** Free space kept around every placed board. */
const BOX_MARGIN = 4
/** A dot keeps this far from every board foot and earlier dot. */
const DOT_CLEARANCE = 8

const BOARD_FONT = "600 0.8rem 'Barlow Semi Condensed', 'Barlow', sans-serif"

/** Board width from its texts, clamped to the CSS `max-width`. */
export function boardWidth(label: TourBoardLabel, textWidth: (text: string) => number): number {
  return Math.min(BOARD_MAX_W, PAD_LEFT + textWidth(label.text) + GAP + textWidth(label.distance) + PAD_RIGHT)
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

const sideOf = (heading: Heading): Side => (heading === 'west' ? 'left' : 'right')
const opposite = (side: Side): Side => (side === 'left' ? 'right' : 'left')

/** Greedy signpost placement in rank order (`tours`, best first). Each tour's board takes the first candidate and side whose
 *  box lies in the viewport and clear of every board placed so far (heading side first). A tour with no such box becomes a
 *  dot after all boards, at the first candidate clear of every foot, else at its first candidate. Result: boards then dots,
 *  each in rank order. */
export function placeSignposts(
  tours: PlaceTour[],
  project: (p: { lat: number; lng: number }) => Pixel,
  measure: (label: TourBoardLabel) => number,
  viewport: Viewport,
): Placement[] {
  const boxes: Box[] = []
  const feet: Pixel[] = []
  const boards: Placement[] = []
  const unplaced: PlaceTour[] = []

  const board = (tour: PlaceTour, width: number): Placement | null => {
    for (const c of tour.candidates) {
      const foot = project(c)
      const preferred = sideOf(c.heading)
      for (const side of [preferred, opposite(preferred)]) {
        const box = boxOf(foot, side, width)
        if (!inside(box, viewport) || boxes.some((b) => overlaps(box, b, BOX_MARGIN))) continue
        boxes.push(box)
        feet.push(foot)
        return { key: tour.key, kind: 'board', lat: c.lat, lng: c.lng, side }
      }
    }
    return null
  }

  for (const tour of tours) {
    if (tour.candidates.length === 0) continue
    const placed = board(tour, measure(tour.label))
    if (placed) boards.push(placed)
    else unplaced.push(tour)
  }

  const dots = unplaced.map((tour): Placement => {
    const spots = tour.candidates.map((c) => ({ c, foot: project(c) }))
    const spot = spots.find(({ foot }) => !feet.some((f) => Math.hypot(f.x - foot.x, f.y - foot.y) < DOT_CLEARANCE)) ?? spots[0]
    feet.push(spot.foot)
    return { key: tour.key, kind: 'dot', lat: spot.c.lat, lng: spot.c.lng, side: sideOf(spot.c.heading) }
  })

  return [...boards, ...dots]
}
