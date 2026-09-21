import L from 'leaflet'
import { Marker, Tooltip } from 'react-leaflet'
import { formatSignpostTime } from '../../format/signpostTime.js'
import type { HutOperator } from '../../hutClass.js'
import { hutSymbolSvg, startSymbolSvg } from './hutSymbol.js'
import './map.css'

export interface TripHutMarker { hutIndex: number; name: string; operator: HutOperator; serviced: boolean }
export interface TripEndMarker { lat: number; lng: number; sourceType: number }
export interface CandidateMapMarker {
  hutIndex: number; lat: number; lng: number; name: string; legInH?: number; legOutH?: number; legH?: number
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)
}

function candidateIcon(c: CandidateMapMarker): L.DivIcon {
  const times = c.legInH !== undefined
    ? `${formatSignpostTime(c.legInH)} · ${formatSignpostTime(c.legOutH ?? 0)}`
    : c.legH !== undefined ? formatSignpostTime(c.legH) : ''
  return L.divIcon({
    className: 'swap-marker',
    html: `<div class="swap-signpost"><strong>${escapeHtml(c.name)}</strong><span>${times}</span></div>`,
    iconSize: [150, 34],
    iconAnchor: [75, 17],
  })
}

/** The active trip: its huts (yellow fill, ink outline, operator shape kept), start/exit symbols and,
 *  while editing, the candidate huts as signposts carrying both leg times. */
export default function TripLayer({ tripHuts, tripEnds, candidates, hutCoordsById, onPickCandidate }: {
  tripHuts: TripHutMarker[]
  tripEnds: TripEndMarker[]
  candidates: CandidateMapMarker[]
  hutCoordsById: Map<number, { lat: number; lng: number }>
  onPickCandidate: (hutIndex: number) => void
}) {
  return (
    <>
      {tripHuts.flatMap((h) => {
        const p = hutCoordsById.get(h.hutIndex)
        if (!p) return []
        const icon = L.divIcon({
          className: 'hut-marker',
          html: hutSymbolSvg({ operator: h.operator, serviced: h.serviced, selected: true, size: 22 }),
          iconSize: [22, 22], iconAnchor: [11, 11],
        })
        return [<Marker key={`h${h.hutIndex}`} position={[p.lat, p.lng]} icon={icon}><Tooltip direction="top">{h.name}</Tooltip></Marker>]
      })}
      {tripEnds.map((e, i) => (
        <Marker
          key={`e${i}`} position={[e.lat, e.lng]}
          icon={L.divIcon({ className: 'start-symbol', html: startSymbolSvg(e.sourceType), iconSize: [16, 16], iconAnchor: [8, 8] })}
        />
      ))}
      {candidates.map((c) => (
        <Marker key={`c${c.hutIndex}`} position={[c.lat, c.lng]} icon={candidateIcon(c)} eventHandlers={{ click: () => onPickCandidate(c.hutIndex) }} />
      ))}
    </>
  )
}
