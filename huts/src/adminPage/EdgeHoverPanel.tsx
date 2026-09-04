import type { Edge, Hover } from './types.js'

// Short display labels + color per OSM sac_scale value, easiest -> hardest (matches
// SAC_SCALE_RANK in data/scripts/06-build-hut-graph.py). Color scales green -> red with grade.
const SAC_SCALE_LABELS: Record<string, { label: string; color: string }> = {
  strolling: { label: 'Spazierweg', color: '#2e7d32' },
  hiking: { label: 'T1 Wandern', color: '#558b2f' },
  mountain_hiking: { label: 'T2 Bergwandern', color: '#9e9d24' },
  demanding_mountain_hiking: { label: 'T3 anspruchsvolles Bergwandern', color: '#f9a825' },
  alpine_hiking: { label: 'T4 Alpinwandern', color: '#ef6c00' },
  demanding_alpine_hiking: { label: 'T5 anspruchsvolles Alpinwandern', color: '#d84315' },
  difficult_alpine_hiking: { label: 'T6 schwieriges Alpinwandern', color: '#b71c1c' },
}

const SPARKLINE_WIDTH = 120
const SPARKLINE_HEIGHT = 32

/**
 * Small inline-SVG height profile for one edge, from its elevation_profile (script 08's
 * downsampled, evenly-distance-spaced elevation series) - no charting library needed at this
 * size. Flat/near-flat profiles get a fallback range so the line doesn't look broken.
 */
function ElevationSparkline({ values }: { values: number[] | null | undefined }) {
  if (!values || values.length < 2) return null

  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1

  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * SPARKLINE_WIDTH
      const y = SPARKLINE_HEIGHT - ((v - min) / range) * SPARKLINE_HEIGHT
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  return (
    <svg
      className="elevation-sparkline"
      width={SPARKLINE_WIDTH}
      height={SPARKLINE_HEIGHT}
      viewBox={`0 0 ${SPARKLINE_WIDTH} ${SPARKLINE_HEIGHT}`}
    >
      <polyline points={points} fill="none" stroke="#e65100" strokeWidth="1.5" />
    </svg>
  )
}

/** Floating panel next to the cursor listing every edge HoverInspector matched, with its
 *  distance/ascent/descent, difficulty badges and elevation sparkline. */
export default function EdgeHoverPanel({
  hover, edges, hutNameById,
}: {
  hover: Hover
  edges: Edge[]
  hutNameById: Map<number, string>
}) {
  return (
    <div className="edge-hover-panel" style={{ left: hover.x + 14, top: hover.y + 14 }}>
      {hover.indices.map((i) => {
        const edge = edges[i]
        return (
          <div key={i} className="edge-hover-row">
            <strong>
              {hutNameById.get(edge.fromId) ?? edge.fromId} → {hutNameById.get(edge.toId) ?? edge.toId}
            </strong>
            <span>
              {(edge.distanceM / 1000).toFixed(1)} km
              {edge.ascentM != null && edge.descentM != null
                ? ` · ↑${Math.round(edge.ascentM)}m ↓${Math.round(edge.descentM)}m`
                : ''}
            </span>
            {(edge.sacScale || edge.viaFerrata) && (
              <span className="edge-difficulty-badges">
                {edge.sacScale && SAC_SCALE_LABELS[edge.sacScale] && (
                  <span
                    className="difficulty-badge"
                    style={{ backgroundColor: SAC_SCALE_LABELS[edge.sacScale].color }}
                  >
                    {SAC_SCALE_LABELS[edge.sacScale].label}
                  </span>
                )}
                {edge.viaFerrata && (
                  <span className="difficulty-badge via-ferrata-badge">Klettersteig</span>
                )}
              </span>
            )}
            <ElevationSparkline values={edge.elevationProfile} />
          </div>
        )
      })}
    </div>
  )
}
