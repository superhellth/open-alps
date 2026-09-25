import type { TourBoardLabel } from './tourBoard.js'

/** A stack spreads into at most this many tour boards, plus one overflow board. */
export const SPREAD_CAP = 8

export interface BoardTour {
  key: string
  label: TourBoardLabel
}

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)
}

function boardBody({ label }: BoardTour): string {
  return `<span class="txt">${escapeHtml(label.text)}</span><span class="km">${escapeHtml(label.distance)}</span>`
}

/** Side of the start point a tour heads to. */
export type Heading = 'east' | 'west'

/** One start point, one tour: the tour board itself is the marker. Its arrow tip sits on the start point and
 *  points toward `heading` (default east: the board lies west of the start, out of the tour's way). */
export function singleHtml(tour: BoardTour, heading: Heading = 'east'): string {
  return `<div class="sign${heading === 'west' ? ' heads-west' : ''}" tabindex="0" role="button" data-tour-key="${escapeHtml(tour.key)}" title="${escapeHtml(tour.label.title)}">${boardBody(tour)}</div>`
}

/** One start point, several tours: a count sign plus every board and a backdrop, hidden until the marker
 *  gets the `spread` class. Board `--up` is its distance above the sign in board pitches (first tour on top). */
export function stackHtml(tours: BoardTour[]): string {
  const shown = tours.slice(0, SPREAD_CAP)
  const hidden = tours.length - shown.length
  const slots = shown.length + (hidden > 0 ? 1 : 0)
  const boards = shown.map((t, i) =>
    `<div class="board" tabindex="0" role="button" style="--up:${slots - i}" data-tour-key="${escapeHtml(t.key)}" title="${escapeHtml(t.label.title)}">${boardBody(t)}</div>`)
  if (hidden > 0) {
    boards.push(`<div class="board overflow" tabindex="0" role="button" style="--up:1" data-overflow title="Alle ${tours.length} Touren in der Liste zeigen"><span class="txt">+${hidden}</span></div>`)
  }
  return `<div class="sign stack-sign" tabindex="0" role="button" aria-label="${tours.length} Touren">${tours.length}</div><div class="spread-backdrop"></div>${boards.join('')}`
}
