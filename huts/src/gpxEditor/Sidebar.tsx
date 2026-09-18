import { useState } from 'react'
import { Box, ButtonBase, Chip, Typography } from '@mui/material'

export interface SidebarLeg {
  leg: number
  snapKnown: boolean
  startUnsnapped: boolean
  endUnsnapped: boolean
  longSegment: boolean
  dirty: boolean
}

export interface SidebarTour {
  name: string
  discontinuous: boolean
  legs: SidebarLeg[]
}

interface SidebarProps {
  tours: SidebarTour[]
  active: { tour: string; leg: number } | null
  onSelect: (tour: string, leg: number) => void
}

export default function Sidebar({ tours, active, onSelect }: SidebarProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const toggle = (name: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (!next.delete(name)) next.add(name)
      return next
    })

  return (
    <Box component="nav" sx={{ width: 300, flexShrink: 0, overflowY: 'auto', borderRight: 1, borderColor: 'divider' }}>
      {tours.map((tour) => (
        <Box key={tour.name}>
          <ButtonBase
            onClick={() => toggle(tour.name)}
            sx={{ width: '100%', justifyContent: 'space-between', px: 2, py: 1, textAlign: 'left' }}
          >
            <Typography variant="subtitle2">{tour.name}</Typography>
            {tour.discontinuous && <Chip size="small" color="warning" label="discontinuous" />}
          </ButtonBase>
          {!collapsed.has(tour.name) &&
            tour.legs.map((l) => (
              <ButtonBase
                key={l.leg}
                onClick={() => onSelect(tour.name, l.leg)}
                sx={{
                  width: '100%', justifyContent: 'flex-start', gap: 0.5, flexWrap: 'wrap', pl: 4, pr: 1, py: 0.75,
                  bgcolor: active?.tour === tour.name && active.leg === l.leg ? 'action.selected' : undefined,
                }}
              >
                <Typography variant="body2" sx={{ mr: 1 }}>Leg {l.leg}</Typography>
                {l.dirty && (
                  <Box aria-label="unsaved edits" role="img"
                    sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: 'primary.main', mr: 0.5 }} />
                )}
                {l.snapKnown && !l.startUnsnapped && !l.endUnsnapped && <Chip size="small" color="success" label="ok" />}
                {l.startUnsnapped && <Chip size="small" color="error" label="start unsnapped" />}
                {l.endUnsnapped && <Chip size="small" color="error" label="end unsnapped" />}
                {l.longSegment && <Chip size="small" color="warning" label="long segment" />}
              </ButtonBase>
            ))}
        </Box>
      ))}
    </Box>
  )
}
