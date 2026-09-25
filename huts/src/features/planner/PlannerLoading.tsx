import { Box, CircularProgress, Typography } from '@mui/material'
import { styles } from './PlannerLoading.styles.js'

export default function PlannerLoading() {
  return (
    <Box sx={styles.root}>
      <CircularProgress />
      <Typography color="text.secondary">Daten werden geladen ...</Typography>
    </Box>
  )
}
