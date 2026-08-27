import { memo, useState } from 'react'
import {
  Alert, Box, Card, CardActionArea, CardContent, MenuItem, Pagination, Select, Table,
  TableBody, TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material'
import type { SelectChangeEvent } from '@mui/material'
import type { SearchResult, TourResult } from '../tourSearch/types.js'
import type { StartPoint } from './types.js'
import SelectedTourMap from './SelectedTourMap.js'
import { PAGE_SIZE, SORT_LABEL, killCounterGuidance, legWaypointLabels, type SortKey } from './helpers.js'

// Memoized so the (up to PAGE_SIZE) result cards, tables and expanded-tour map are only
// reconciled when the search results/sort/paging actually change — not on every keystroke in the
// sibling filter form (every prop here is either a primitive, a setState function — stable by
// React's guarantee — or a value already memoized upstream, so an unrelated form-field edit
// leaves every prop reference-equal and this whole subtree bails out).
const ResultsPanel = memo(function ResultsPanel({
  result, displayedChains, pageChains, page, pageCount, setPage,
  sortKey, setSortKey, regionCenterId, setRegionCenterId, regionMenuItems,
  regionRadiusKm, setRegionRadiusKm, hutNameById, hutCoordsById, startById, startLabel,
}: {
  result: SearchResult
  displayedChains: TourResult[]
  pageChains: TourResult[]
  page: number
  pageCount: number
  setPage: (p: number) => void
  sortKey: SortKey
  setSortKey: (k: SortKey) => void
  regionCenterId: number | 'all'
  setRegionCenterId: (id: number | 'all') => void
  regionMenuItems: React.ReactNode
  regionRadiusKm: string
  setRegionRadiusKm: (v: string) => void
  hutNameById: Map<number, string>
  hutCoordsById: Map<number, { lat: number; lng: number }>
  startById: Map<number, StartPoint>
  startLabel: (startId: number) => string
}) {
  const [expandedChain, setExpandedChain] = useState<number | null>(null)

  return (
    <>
      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <Typography color="text.secondary">
          {displayedChains.length} Tour{displayedChains.length === 1 ? '' : 'en'} gefunden
        </Typography>
        <Select size="small" value={sortKey} onChange={(e: SelectChangeEvent) => setSortKey(e.target.value as SortKey)}>
          {(Object.keys(SORT_LABEL) as SortKey[]).map((key) => (
            <MenuItem key={key} value={key}>
              Sortieren: {SORT_LABEL[key]}
            </MenuItem>
          ))}
        </Select>
        <Select
          size="small"
          value={String(regionCenterId)}
          onChange={(e: SelectChangeEvent) => setRegionCenterId(e.target.value === 'all' ? 'all' : Number(e.target.value))}
        >
          <MenuItem value="all">Alle Regionen</MenuItem>
          {regionMenuItems}
        </Select>
        {regionCenterId !== 'all' && (
          <TextField
            size="small"
            type="number"
            label="Radius (km)"
            value={regionRadiusKm}
            onChange={(e) => setRegionRadiusKm(e.target.value)}
            sx={{ width: 120 }}
          />
        )}
      </Box>

      {displayedChains.length === 0 && (
        <Box>
          <Typography>Keine Touren gefunden. Filter lockern und erneut versuchen.</Typography>
          {killCounterGuidance(result.killCounters).map((msg, i) => (
            <Alert key={i} severity="info" sx={{ mt: 1 }}>
              {msg}
            </Alert>
          ))}
        </Box>
      )}

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {pageChains.map((chain, i) => {
          const chainIndex = (page - 1) * PAGE_SIZE + i
          const isExpanded = expandedChain === chainIndex
          return (
            <Card key={chainIndex} variant="outlined">
              <CardActionArea onClick={() => setExpandedChain(isExpanded ? null : chainIndex)}>
                <CardContent>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    {startLabel(chain.startId)} → … → {startLabel(chain.exitStartId)}
                  </Typography>
                  <Typography color="text.secondary" variant="body2">
                    {chain.totalDurationH.toFixed(1)} h · ↑{Math.round(chain.totalAscentM)}m ↓
                    {Math.round(chain.totalDescentM)}m · {(chain.totalDistanceM / 1000).toFixed(1)} km ·{' '}
                    {chain.huts.length} Etappen
                  </Typography>
                </CardContent>
              </CardActionArea>
              {isExpanded && (
                <CardContent sx={{ pt: 0 }}>
                  <Typography variant="body2" sx={{ mb: 1 }}>
                    {startLabel(chain.startId)}
                    {chain.huts.map((h) => ` → ${hutNameById.get(h) ?? h}`).join('')}
                    {' → '}
                    {startLabel(chain.exitStartId)}
                  </Typography>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Etappe</TableCell>
                        <TableCell align="right">Dauer</TableCell>
                        <TableCell align="right">↑</TableCell>
                        <TableCell align="right">↓</TableCell>
                        <TableCell align="right">Distanz</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {legWaypointLabels(chain, startLabel, hutNameById).map((label, legIndex) => {
                        const leg = chain.legs[legIndex]
                        return (
                          <TableRow key={legIndex}>
                            <TableCell>{label}</TableCell>
                            <TableCell align="right">{leg.durationH.toFixed(1)} h</TableCell>
                            <TableCell align="right">{Math.round(leg.ascentM)}m</TableCell>
                            <TableCell align="right">{Math.round(leg.descentM)}m</TableCell>
                            <TableCell align="right">{(leg.distanceM / 1000).toFixed(1)} km</TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                  <Box sx={{ mt: 1 }}>
                    <SelectedTourMap chain={chain} hutCoordsById={hutCoordsById} startById={startById} />
                  </Box>
                </CardContent>
              )}
            </Card>
          )
        })}
      </Box>

      {pageCount > 1 && (
        <Pagination count={pageCount} page={page} onChange={(_e, p) => setPage(p)} sx={{ alignSelf: 'center' }} />
      )}
    </>
  )
})

export default ResultsPanel
