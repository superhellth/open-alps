import { useEffect, useState } from 'react'
import { Box, Button, Chip, List, ListItemButton, MenuItem, Pagination, Select, Typography } from '@mui/material'
import { formatSignpostTime } from '../format/signpostTime.js'
import { hutClassBadge } from '../hutClass.js'
import type { HutClass } from '../hutClass.js'
import { SIGNPOST_FONT } from '../theme.js'
import { SORT_LABEL } from './rankTours.js'
import type { SortKey } from './rankTours.js'
import type { PlannerTour } from './tours.js'

const PAGE_SIZE = 25

export default function ResultsList({
  tours, selectionActive, totalMatches, noMatches, sortKey, onSortChange,
  hutNameById, hutClassByIndex, startLabel, onPreview, onPick, onShowBest, isFull,
}: {
  tours: PlannerTour[]
  selectionActive: boolean
  totalMatches: number
  noMatches: boolean
  sortKey: SortKey
  onSortChange: (key: SortKey) => void
  hutNameById: Map<number, string>
  hutClassByIndex: Map<number, HutClass>
  startLabel: (startId: number) => string
  onPreview: (tour: PlannerTour | null) => void
  onPick: (tour: PlannerTour) => void
  onShowBest: () => void
  isFull?: (tour: PlannerTour) => boolean
}) {
  const [page, setPage] = useState(1)
  useEffect(() => setPage(1), [tours])

  if (noMatches) {
    return <Typography sx={{ p: 2 }}>Keine Touren für diese Filter. Mehr Tage oder längere Gehzeit pro Tag zulassen.</Typography>
  }
  if (!selectionActive) {
    return (
      <Box sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 1, alignItems: 'flex-start' }}>
        {totalMatches > 0 && (
          <Button variant="contained" onClick={onShowBest}>{totalMatches} Touren anzeigen</Button>
        )}
        <Typography color="text.secondary">
          Marker sind Startpunkte, die Zahl ist die Anzahl passender Touren dort. Marker anklicken, um die Touren eines Gebiets zu sehen.
        </Typography>
      </Box>
    )
  }

  const pageCount = Math.max(1, Math.ceil(tours.length / PAGE_SIZE))
  const shown = tours.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <Box sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography color="text.secondary">{tours.length} Tour{tours.length === 1 ? '' : 'en'} in diesem Gebiet</Typography>
        <Select size="small" value={sortKey} onChange={(e) => onSortChange(e.target.value as SortKey)} inputProps={{ 'aria-label': 'Sortierung' }}>
          {(Object.keys(SORT_LABEL) as SortKey[]).map((key) => <MenuItem key={key} value={key}>{SORT_LABEL[key]}</MenuItem>)}
        </Select>
      </Box>
      <List disablePadding>
        {shown.map((tour, i) => {
          const names = tour.huts.map((h) => hutNameById.get(h) ?? String(h))
          return (
            <ListItemButton
              key={`${tour.startId}-${tour.official?.tourId ?? ''}-${tour.huts.join('.')}-${i}`}
              onMouseEnter={() => onPreview(tour)} onMouseLeave={() => onPreview(null)}
              onFocus={() => onPreview(tour)} onBlur={() => onPreview(null)}
              onClick={() => onPick(tour)}
              sx={{ display: 'block', borderBottom: '1px solid', borderColor: 'divider' }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, fontFamily: SIGNPOST_FONT, fontWeight: 600 }}>
                <span>{names.join(' → ')}</span>
                <span>{formatSignpostTime(tour.totalDurationH)}</span>
              </Box>
              <Typography variant="caption" color="text.secondary" component="div">
                {tour.legs.length} Tage · ↑ {Math.round(tour.totalAscentM).toLocaleString('de-DE')} m · {(tour.totalDistanceM / 1000).toFixed(1)} km · ab {startLabel(tour.startId)}
              </Typography>
              <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                {isFull?.(tour) && <Chip size="small" color="warning" label="voll" />}
                {tour.official && <Chip size="small" label={`Offiziell: ${tour.official.name}`} />}
                {tour.huts.map((h) => {
                  const cls = hutClassByIndex.get(h)
                  return cls ? <Chip key={h} size="small" variant="outlined" label={hutClassBadge(cls)} /> : null
                })}
              </Box>
            </ListItemButton>
          )
        })}
      </List>
      {pageCount > 1 && <Pagination count={pageCount} page={page} onChange={(_e, p) => setPage(p)} size="small" />}
    </Box>
  )
}
