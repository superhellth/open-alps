import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import LoopIcon from '@mui/icons-material/Loop'
import type { TourBoardLabel } from './tourBoard.js'
import type { Side } from './placeSignposts.js'

export interface BoardTour {
  key: string
  label: TourBoardLabel
}

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)
}

/** Loop pictogram marking a round trip's board. */
const LOOP_ICON = `<span class="loop" aria-hidden="true">${renderToStaticMarkup(createElement(LoopIcon))}</span>`

function boardBody({ label }: BoardTour): string {
  return `${label.roundTrip ? LOOP_ICON : ''}<span class="txt">${escapeHtml(label.text)}</span><span class="detail">${escapeHtml(label.detail)}</span>`
}

const MAST = '<span class="mast"></span>'
/** Mast and foot dot on the anchor; both ignore the pointer so the route line under them stays hoverable. */
const MAST_AND_FOOT = `${MAST}<span class="foot"></span>`

const tourAttrs = ({ key, label }: BoardTour) =>
  `tabindex="0" role="button" data-tour-key="${escapeHtml(key)}" title="${escapeHtml(label.title)}"`

/** One tour: a board hanging by its tail from a mast whose foot stands on the anchor. The arrow points away from the mast
 *  (`right`: arrow on the right). */
export function singleHtml(tour: BoardTour, side: Side): string {
  return `${MAST_AND_FOOT}<div class="sign side-${side}" ${tourAttrs(tour)}>${boardBody(tour)}</div>`
}

/** A tour with no room for its board: a foot dot on the anchor plus the board on a mast, hidden until the marker
 *  gets the `previewing` class. The preview ignores the pointer. */
export function dotHtml(tour: BoardTour, side: Side): string {
  return `<span class="dot" ${tourAttrs(tour)} aria-label="${escapeHtml(tour.label.title)}"></span>`
    + `<span class="preview" aria-hidden="true">${MAST}<div class="sign side-${side}">${boardBody(tour)}</div></span>`
}
