import L from 'leaflet'
import { Marker, Tooltip } from 'react-leaflet'
import { formatSignpostTime } from '@/format/signpostTime.js'
import type { HutOperator } from '@/data/hutClass.js'
import type { SourceType } from '@/tourSearch/types.js'
import { hutSymbolSvg, startSymbolSvg } from './hutSymbol.js'
import './map.css'

export interface TripHutMarker { hutIndex: number; name: string; operator: HutOperator; serviced: boolean }
export interface TripEndMarker { lat: number; lng: number; sourceType: number }
export interface CandidateMapMarker {
  hutIndex?: number
  startId?: number
  sourceType?: SourceType
  name?: string
  legInH?: number
  legOutH?: number
  legH?: number
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)
}

function candidateTimes(c: CandidateMapMarker): string {
  if (c.legInH !== undefined) return `${formatSignpostTime(c.legInH)} · ${formatSignpostTime(c.legOutH ?? 0)}`
  if (c.legH !== undefined) return formatSignpostTime(c.legH)
  return ''
}

function candidateIcon(c: CandidateMapMarker, label: string): L.DivIcon {
  return L.divIcon({
    className: 'swap-marker',
    html: `<div class="swap-signpost"><strong>${escapeHtml(label)}</strong><span>${candidateTimes(c)}</span></div>`,
    iconSize: [150, 34],
    iconAnchor: [75, 17],
  })
}

/** The active trip: its huts (yellow fill, ink outline, operator shape kept), start/exit symbols
 *  and, while editing, the candidate huts or start/exit points as signposts. A hut candidate reads
 *  its position from hutCoordsById; a start/exit candidate from candidateStartCoords. */
export default function TripLayer({ tripHuts, tripEnds, candidates, hutCoordsById, candidateStartCoords, onPickCandidate }: {
  tripHuts: TripHutMarker[]
  tripEnds: TripEndMarker[]
  candidates: CandidateMapMarker[]
  hutCoordsById: Map<number, { lat: number; lng: number }>
  candidateStartCoords: Map<number, { lat: number; lng: number }>
  onPickCandidate: (arg: { hutIndex?: number; startId?: number }) => void
}) {
  return (
    <>
      {tripHuts.flatMap((h) => {
        const p = hutCoordsById.get(h.hutIndex)
        if (!p) return []
        const icon = L.divIcon({
          className: 'hut-marker',
          html: hutSymbolSvg({ serviced: h.serviced, selected: true, size: 22 }),
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
      {candidates.flatMap((c) => {
        if (c.hutIndex !== undefined) {
          const p = hutCoordsById.get(c.hutIndex)
          if (!p) return []
          return [
            <Marker
              key={`ch${c.hutIndex}`} position={[p.lat, p.lng]} icon={candidateIcon(c, c.name ?? String(c.hutIndex))}
              eventHandlers={{ click: () => onPickCandidate({ hutIndex: c.hutIndex }) }}
            />,
          ]
        }
        if (c.startId !== undefined) {
          const p = candidateStartCoords.get(c.startId)
          if (!p) return []
          return [
            <Marker
              key={`cs${c.startId}`} position={[p.lat, p.lng]} icon={candidateIcon(c, c.name ?? String(c.startId))}
              eventHandlers={{ click: () => onPickCandidate({ startId: c.startId }) }}
            />,
          ]
        }
        return []
      })}
    </>
  )
}
