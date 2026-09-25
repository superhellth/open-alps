import { Box, Typography } from '@mui/material'
import { styles } from './FirstVisitPrompt.styles.js'

export default function FirstVisitPrompt() {
  return (
    <Box
      role="note"
      sx={styles.root}
    >
      <Typography variant="body2">
        Die Marker sind Startpunkte, die Zahl darin ist die Anzahl passender Touren. Zoom oder Klick zeigt die Touren dieses Gebiets.
      </Typography>
    </Box>
  )
}
