import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { HutSymbol, StartSymbol } from './StopSymbol.js'

/** HutSymbol as markup for a Leaflet divIcon. */
export function hutSymbolSvg(props: { serviced: boolean; selected?: boolean; size?: number }): string {
  return renderToStaticMarkup(createElement(HutSymbol, props))
}

/** StartSymbol as markup for a Leaflet divIcon. */
export function startSymbolSvg(sourceType: number, size = 16): string {
  return renderToStaticMarkup(createElement(StartSymbol, { sourceType, size }))
}
