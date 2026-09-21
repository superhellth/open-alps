import { OPERATOR_SHAPE } from '../../hutClass.js'
import type { HutOperator } from '../../hutClass.js'
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_PARTNER } from '../../tourSearch/types.js'
import { tokens } from '../../theme.js'

const { ink, paper, signpost } = tokens

/** Hut marker as inline SVG for a Leaflet divIcon: house = AV, circle = other; ink fill = serviced,
 *  ink outline = self-catering; selected = signpost-yellow fill with ink outline (shape kept). */
export function hutSymbolSvg({ operator, serviced, selected = false, size = 18 }:
  { operator: HutOperator; serviced: boolean; selected?: boolean; size?: number }): string {
  const fill = selected ? signpost : serviced ? ink : paper
  const stroke = `stroke="${ink}" stroke-width="${selected || !serviced ? 2 : 1}"`
  const shape = OPERATOR_SHAPE[operator] === 'house'
    ? `<polygon points="9,1.5 16.5,8 14.5,8 14.5,16 3.5,16 3.5,8 1.5,8" fill="${fill}" ${stroke}/>`
    : `<circle cx="9" cy="9" r="6.5" fill="${fill}" ${stroke}/>`
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 18 18">${shape}</svg>`
}

/** Small start/exit symbols shown on a trip: train / P / village. */
export function startSymbolSvg(sourceType: number, size = 16): string {
  const frame = `<rect x="0.75" y="0.75" width="14.5" height="14.5" rx="2" fill="${paper}" stroke="${ink}" stroke-width="1.5"/>`
  let glyph: string
  if (sourceType === SOURCE_TYPE_PARKING) {
    glyph = `<text x="8" y="12" text-anchor="middle" font-size="10" font-weight="700" fill="${ink}">P</text>`
  } else if (sourceType === SOURCE_TYPE_PARTNER) {
    glyph = `<polygon points="8,3.5 12.5,7.5 11.5,7.5 11.5,12.5 4.5,12.5 4.5,7.5 3.5,7.5" fill="${ink}"/>`
  } else {
    glyph = `<rect x="4" y="3.5" width="8" height="7" rx="1.5" fill="${ink}"/><circle cx="6" cy="12.5" r="1" fill="${ink}"/><circle cx="10" cy="12.5" r="1" fill="${ink}"/>`
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 16 16">${frame}${glyph}</svg>`
}
