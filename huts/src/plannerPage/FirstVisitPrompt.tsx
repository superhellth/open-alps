import { Box, Typography } from '@mui/material'

export default function FirstVisitPrompt() {
  return (
    <Box
      role="note"
      sx={{ position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)', zIndex: 1000, bgcolor: 'background.paper', border: '2px solid', borderColor: 'secondary.main', px: 2, py: 1, maxWidth: 420, pointerEvents: 'none' }}
    >
      <Typography variant="body2">
        Die Marker sind Startpunkte, die Zahl darin ist die Anzahl passender Touren. Zoom oder Klick zeigt die Touren dieses Gebiets.
      </Typography>
    </Box>
  )
}
