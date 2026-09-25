import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { Box, Button, Chip, List, ListItemButton, Pagination, Typography } from '@mui/material'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import { formatSignpostTime } from '@/format/signpostTime.js'
import { tokens } from '@/ui/tokens.js'
import { SORT_LABEL } from './rankTours.js'
import type { SortDir, SortKey } from './rankTours.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import { styles } from './ResultsList.styles.js'

const PAGE_SIZE = 25
const CHAIN_SPELLED_OUT_MAX = 3

/** Full chain up to 3 huts; longer tours show first – last plus how many stops were folded in. */
function hutChain(tour: PlannerTour, hutNameById: Map<number, string>): { text: string; foldedCount: number } {
  const names = tour.huts.map((h) => hutNameById.get(h) ?? String(h))
  if (names.length <= CHAIN_SPELLED_OUT_MAX) return { text: names.join(' – '), foldedCount: 0 }
  return { text: `${names[0]} – ${names[names.length - 1]}`, foldedCount: names.length - 2 }
}

/** Bold signpost-yellow fill on the metric matching the current sort, muted text otherwise —
 *  the app's only accent color is a fill, never a text color. */
function statStyle(active: boolean): CSSProperties {
  return active
    ? { fontWeight: 700, background: tokens.signpost, color: tokens.ink, padding: '0 4px', borderRadius: 2 }
    : { color: 'inherit' }
}

export default function ResultsList({
  tours, totalCount, onShowAll, isHighlighted, noMatches, sortKey, onSortChange, sortDir, onSortDirChange,
  hutNameById, onPreview, onPick, onOpenFilters,
}: {
  tours: PlannerTour[]
  /** All tours matching the filters, regardless of map zoom or focus. */
  totalCount: number
  /** Lifts the map-based limit and zooms the map out to every tour. */
  onShowAll: () => void
  /** True for tours highlighted on the map (hovered route or hovered start bubble). */
  isHighlighted: (tour: PlannerTour) => boolean
  noMatches: boolean
  sortKey: SortKey
  onSortChange: (key: SortKey) => void
  sortDir: SortDir
  onSortDirChange: (dir: SortDir) => void
  hutNameById: Map<number, string>
  onPreview: (tour: PlannerTour | null) => void
  onPick: (tour: PlannerTour) => void
  onOpenFilters: () => void
}) {
  const [page, setPage] = useState(1)
  useEffect(() => setPage(1), [tours])

  if (noMatches) {
    return (
      <Box sx={styles.noMatches}>
        <Typography>Keine Touren für diese Filter. Mehr Tage oder längere Gehzeit pro Tag zulassen.</Typography>
        <Button variant="outlined" onClick={onOpenFilters}>Filter anpassen</Button>
      </Box>
    )
  }
  const pageCount = Math.max(1, Math.ceil(tours.length / PAGE_SIZE))
  const shown = tours.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column' }}>
      <Box sx={styles.sortBar}>
        {(Object.keys(SORT_LABEL) as SortKey[]).map((key) => {
          const active = key === sortKey
          return (
            <Chip
              key={key} size="small"
              label={
                <Box sx={styles.sortChipLabel}>
                  {SORT_LABEL[key]}
                  {active && key !== 'fit' && (sortDir === 'asc' ? <ArrowUpwardIcon sx={{ fontSize: 14 }} /> : <ArrowDownwardIcon sx={{ fontSize: 14 }} />)}
                </Box>
              }
              onClick={() => {
                if (!active) onSortChange(key)
                else if (key !== 'fit') onSortDirChange(sortDir === 'asc' ? 'desc' : 'asc')
              }}
              sx={styles.sortChip(active)}
            />
          )
        })}
      </Box>
      {tours.length < totalCount && (
        <Box sx={{ px: 1, pt: 1 }}>
          <Button size="small" color="inherit" onClick={onShowAll} sx={{ color: 'text.secondary' }}>
            ← Alle {totalCount} Touren anzeigen
          </Button>
        </Box>
      )}
      {shown.length === 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
          Keine Touren im aktuellen Kartenausschnitt. Karte verschieben oder herauszoomen.
        </Typography>
      )}
      <List disablePadding sx={{ px: 2, pb: 2 }}>
        {shown.map((tour, i) => {
          const chain = hutChain(tour, hutNameById)
          return (
            <ListItemButton
              key={`${tour.startId}-${tour.official?.tourId ?? ''}-${tour.huts.join('.')}-${i}`}
              onMouseEnter={() => onPreview(tour)} onMouseLeave={() => onPreview(null)}
              onFocus={() => onPreview(tour)} onBlur={() => onPreview(null)}
              onClick={() => onPick(tour)}
              sx={styles.row(isHighlighted(tour))}
            >
              <Box sx={styles.chainRow}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>
                  {chain.text}
                </span>
                {chain.foldedCount > 0 && <Chip size="small" label={`+${chain.foldedCount} Hütten`} sx={{ flexShrink: 0 }} />}
              </Box>
              <Box sx={styles.statRow}>
                <span style={{ whiteSpace: 'nowrap', ...statStyle(sortKey === 'duration') }}>{formatSignpostTime(tour.totalDurationH)}</span>
                <span style={{ whiteSpace: 'nowrap', ...statStyle(sortKey === 'distance') }}>{(tour.totalDistanceM / 1000).toFixed(1)} km</span>
              </Box>
              <Typography variant="caption" color="text.secondary" component="div">
                {tour.legs.length} Tage ·{' '}
                <span style={{ whiteSpace: 'nowrap', ...statStyle(sortKey === 'ascent') }}>↑ {Math.round(tour.totalAscentM).toLocaleString('de-DE')} m</span>
                {' '}· ↓ {Math.round(tour.totalDescentM).toLocaleString('de-DE')} m
              </Typography>
              {tour.official && (
                <Box sx={styles.officialRow}>
                  <Chip size="small" label={`Offiziell: ${tour.official.name}`} />
                </Box>
              )}
            </ListItemButton>
          )
        })}
      </List>
      {pageCount > 1 && <Pagination sx={{ px: 2, pb: 2 }} count={pageCount} page={page} onChange={(_e, p) => setPage(p)} size="small" />}
    </Box>
  )
}
