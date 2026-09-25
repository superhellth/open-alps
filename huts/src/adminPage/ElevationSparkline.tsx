const SPARKLINE_WIDTH = 120
const SPARKLINE_HEIGHT = 32

/**
 * Small inline-SVG height profile for one edge's elevation profile (downsampled,
 * evenly-distance-spaced elevation series) - no charting library needed at this size. Flat/
 * near-flat profiles get a fallback range so the line doesn't look broken.
 */
export default function ElevationSparkline({ values }: { values: number[] | null | undefined }) {
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
