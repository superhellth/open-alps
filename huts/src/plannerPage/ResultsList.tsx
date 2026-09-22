import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { Box, Button, Chip, List, ListItemButton, MenuItem, Pagination, Select, Typography } from '@mui/material'
import { formatSignpostTime } from '../format/signpostTime.js'
import { SIGNPOST_FONT, tokens } from '../theme.js'
import { SORT_LABEL } from './rankTours.js'
import type { SortKey } from './rankTours.js'
import type { PlannerTour } from './tours.js'

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
  tours, noMatches, sortKey, onSortChange,
  hutNameById, onPreview, onPick, onOpenFilters,
}: {
  tours: PlannerTour[]
  noMatches: boolean
  sortKey: SortKey
  onSortChange: (key: SortKey) => void
  hutNameById: Map<number, string>
  onPreview: (tour: PlannerTour | null) => void
  onPick: (tour: PlannerTour) => void
  onOpenFilters: () => void
}) {
  const [page, setPage] = useState(1)
  useEffect(() => setPage(1), [tours])

  if (noMatches) {
    return (
      <Box sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 1, alignItems: 'flex-start' }}>
        <Typography>Keine Touren für diese Filter. Mehr Tage oder längere Gehzeit pro Tag zulassen.</Typography>
        <Button variant="outlined" onClick={onOpenFilters}>Filter anpassen</Button>
      </Box>
    )
  }
  const pageCount = Math.max(1, Math.ceil(tours.length / PAGE_SIZE))
  const shown = tours.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <Box sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography color="text.secondary">{tours.length} Tour{tours.length === 1 ? '' : 'en'} gefunden</Typography>
        <Select size="small" value={sortKey} onChange={(e) => onSortChange(e.target.value as SortKey)} inputProps={{ 'aria-label': 'Sortierung' }}>
          {(Object.keys(SORT_LABEL) as SortKey[]).map((key) => <MenuItem key={key} value={key}>{SORT_LABEL[key]}</MenuItem>)}
        </Select>
      </Box>
      <List disablePadding>
        {shown.map((tour, i) => {
          const chain = hutChain(tour, hutNameById)
          return (
            <ListItemButton
              key={`${tour.startId}-${tour.official?.tourId ?? ''}-${tour.huts.join('.')}-${i}`}
              onMouseEnter={() => onPreview(tour)} onMouseLeave={() => onPreview(null)}
              onFocus={() => onPreview(tour)} onBlur={() => onPreview(null)}
              onClick={() => onPick(tour)}
              sx={{ display: 'block', borderBottom: '1px solid', borderColor: 'divider' }}
            >
              <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, fontFamily: SIGNPOST_FONT, fontWeight: 600 }}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>
                  {chain.text}
                </span>
                {chain.foldedCount > 0 && <Chip size="small" label={`+${chain.foldedCount} Hütten`} sx={{ flexShrink: 0 }} />}
              </Box>
              <Box sx={{ display: 'flex', flexWrap: 'nowrap', gap: 2, mt: 0.5, color: 'text.secondary' }}>
                <span style={{ whiteSpace: 'nowrap', ...statStyle(sortKey === 'duration') }}>{formatSignpostTime(tour.totalDurationH)}</span>
                <span style={{ whiteSpace: 'nowrap', ...statStyle(sortKey === 'distance') }}>{(tour.totalDistanceM / 1000).toFixed(1)} km</span>
              </Box>
              <Typography variant="caption" color="text.secondary" component="div">
                {tour.legs.length} Tage ·{' '}
                <span style={{ whiteSpace: 'nowrap', ...statStyle(sortKey === 'ascent') }}>↑ {Math.round(tour.totalAscentM).toLocaleString('de-DE')} m</span>
                {' '}· ↓ {Math.round(tour.totalDescentM).toLocaleString('de-DE')} m
              </Typography>
              {tour.official && (
                <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                  <Chip size="small" label={`Offiziell: ${tour.official.name}`} />
                </Box>
              )}
            </ListItemButton>
          )
        })}
      </List>
      {pageCount > 1 && <Pagination count={pageCount} page={page} onChange={(_e, p) => setPage(p)} size="small" />}
    </Box>
  )
}
