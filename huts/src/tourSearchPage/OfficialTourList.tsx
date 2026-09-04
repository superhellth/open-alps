import { memo, useState } from 'react'
import {
  Box, Card, CardActionArea, CardContent, IconButton, Table, TableBody, TableCell, TableHead, TableRow, Typography,
} from '@mui/material'
import type { OfficialTourLeg, OfficialTourView } from '../tourSearch/officialTours.js'
import { hutClassBadge, OPERATOR_COLOR, type HutClass } from '../hutClass.js'

function waypointLabel(
  endpoint: OfficialTourLeg['from'],
  hutNameById: Map<number, string>,
  startLabel: (startId: number) => string,
): string {
  return endpoint.type === 'hut' ? (hutNameById.get(endpoint.id) ?? String(endpoint.id)) : startLabel(endpoint.id)
}

const OfficialTourList = memo(function OfficialTourList({
  tours, hutNameById, hutClassByIndex, startLabel, selectedTourId, setSelectedTourId,
}: {
  tours: OfficialTourView[]
  hutNameById: Map<number, string>
  hutClassByIndex: Map<number, HutClass>
  startLabel: (startId: number) => string
  selectedTourId: number | null
  setSelectedTourId: (id: number | null) => void
}) {
  const [collapsed, setCollapsed] = useState(false)

  if (collapsed) {
    return (
      <Box sx={{ width: 40, flexShrink: 0, borderRight: '1px solid #e0e0e0', display: 'flex', justifyContent: 'center', pt: 1 }}>
        <IconButton size="small" onClick={() => setCollapsed(false)} aria-label="Tourenliste einblenden">
          ›
        </IconButton>
      </Box>
    )
  }

  return (
    <Box sx={{ width: '25%', minWidth: 280, flexShrink: 0, borderRight: '1px solid #e0e0e0', overflowY: 'auto', p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography color="text.secondary">
          {tours.length} offizielle Tour{tours.length === 1 ? '' : 'en'}
        </Typography>
        <IconButton size="small" onClick={() => setCollapsed(true)} aria-label="Tourenliste minimieren">
          ‹
        </IconButton>
      </Box>

      {tours.length === 0 && (
        <Typography>
          Für die offiziellen Touren liegen derzeit keine durchgehend berechneten Routen vor.
        </Typography>
      )}

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {tours.map((tour) => {
          const isExpanded = selectedTourId === tour.tourId
          return (
            <Card key={tour.tourId} variant="outlined">
              <CardActionArea onClick={() => setSelectedTourId(isExpanded ? null : tour.tourId)}>
                <CardContent>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    {tour.name}
                  </Typography>
                  <Typography color="text.secondary" variant="body2">
                    {tour.totalDurationH.toFixed(1)} h · ↑{Math.round(tour.totalAscentM)}m ↓
                    {Math.round(tour.totalDescentM)}m · {(tour.totalDistanceM / 1000).toFixed(1)} km ·{' '}
                    {tour.legs.length} Etappen
                  </Typography>
                </CardContent>
              </CardActionArea>
              {isExpanded && (
                <CardContent sx={{ pt: 0 }}>
                  <Typography variant="body2" sx={{ mb: 1 }}>
                    {waypointLabel(tour.legs[0].from, hutNameById, startLabel)}
                    {tour.legs.map((leg) => {
                      const cls = leg.to.type === 'hut' ? hutClassByIndex.get(leg.to.id) : undefined
                      return (
                        <span key={leg.legIndex}>
                          {' → '}
                          {waypointLabel(leg.to, hutNameById, startLabel)}
                          {cls && (
                            <span
                              style={{
                                marginLeft: 4, padding: '0 4px', borderRadius: 3, fontSize: '0.7rem',
                                color: '#fff', backgroundColor: OPERATOR_COLOR[cls.operator],
                              }}
                            >
                              {hutClassBadge(cls)}
                            </span>
                          )}
                        </span>
                      )
                    })}
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
                      {tour.legs.map((leg) => (
                        <TableRow key={leg.legIndex}>
                          <TableCell>
                            Etappe {leg.legIndex + 1}: {waypointLabel(leg.from, hutNameById, startLabel)} → {waypointLabel(leg.to, hutNameById, startLabel)}
                          </TableCell>
                          <TableCell align="right">{leg.durationH.toFixed(1)} h</TableCell>
                          <TableCell align="right">{Math.round(leg.ascentM)}m</TableCell>
                          <TableCell align="right">{Math.round(leg.descentM)}m</TableCell>
                          <TableCell align="right">{(leg.distanceM / 1000).toFixed(1)} km</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              )}
            </Card>
          )
        })}
      </Box>
    </Box>
  )
})

export default OfficialTourList
