import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import DirectionsTransitIcon from '@mui/icons-material/DirectionsTransit'
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_PARTNER } from '@/tourSearch/types.js'
import { tokens } from '@/ui/theme.js'

const { ink, paper, signpost } = tokens

/** Size of a trip stop's symbol in the sidebar (stage rail and height profile). */
export const STOP_SYMBOL_SIZE = 16

/** Inner paths of the MUI transit pictogram (24x24 viewBox), scaled into the 16px start frame. */
const TRANSIT_PATHS = renderToStaticMarkup(createElement(DirectionsTransitIcon)).replace(/^<svg[^>]*>|<\/svg>$/g, '')

/** Placement inside a parent svg; omitted for a standalone symbol. */
interface At { x?: number; y?: number }

/** House shape for every hut; ink fill = serviced, ink outline = self-catering; selected =
 *  signpost-yellow fill with ink outline. */
export function HutSymbol({ serviced, selected = false, size = 18, x, y }:
  { serviced: boolean; selected?: boolean; size?: number } & At) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" x={x} y={y} width={size} height={size} viewBox="0 0 18 18">
      <polygon
        points="9,1.5 16.5,8 14.5,8 14.5,16 3.5,16 3.5,8 1.5,8"
        fill={selected ? signpost : serviced ? ink : paper} stroke={ink} strokeWidth={selected || !serviced ? 2 : 1}
      />
    </svg>
  )
}

/** Start/exit symbol: transit stop / P / village in a frame. */
export function StartSymbol({ sourceType, size = 16, x, y }: { sourceType: number; size?: number } & At) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" x={x} y={y} width={size} height={size} viewBox="0 0 16 16">
      <rect x="0.75" y="0.75" width="14.5" height="14.5" rx="2" fill={paper} stroke={ink} strokeWidth="1.5" />
      {sourceType === SOURCE_TYPE_PARKING
        ? <text x="8" y="12" textAnchor="middle" fontSize="10" fontWeight="700" fill={ink}>P</text>
        : sourceType === SOURCE_TYPE_PARTNER
          ? <polygon points="8,3.5 12.5,7.5 11.5,7.5 11.5,12.5 4.5,12.5 4.5,7.5 3.5,7.5" fill={ink} />
          : <g transform="translate(2 2) scale(0.5)" fill={ink} dangerouslySetInnerHTML={{ __html: TRANSIT_PATHS }} />}
    </svg>
  )
}

/** A stop of an open trip: a hut (outlined when it no longer resolves) or the start/exit point. */
export type StopMark = { type: 'hut'; changed: boolean } | { type: 'end'; sourceType: number }

/** A trip stop as the map draws it: trip huts in signpost yellow, a changed hut as an outline. */
export function StopSymbol({ mark, size = STOP_SYMBOL_SIZE, x, y }: { mark: StopMark; size?: number } & At) {
  return mark.type === 'hut'
    ? <HutSymbol serviced={false} selected={!mark.changed} size={size} x={x} y={y} />
    : <StartSymbol sourceType={mark.sourceType} size={size} x={x} y={y} />
}
