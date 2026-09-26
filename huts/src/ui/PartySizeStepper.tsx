import { Box, Button, Typography } from '@mui/material'
import { styles } from './PartySizeStepper.styles.js'

export const MAX_PARTY_SIZE = 25

/** "2 Pers. [−][+]", clamped to 1…MAX_PARTY_SIZE. */
export default function PartySizeStepper({ value, onChange, disabled = false }: {
  value: number
  onChange: (partySize: number) => void
  disabled?: boolean
}) {
  return (
    <Box sx={styles.row}>
      <Typography>{value} Pers.</Typography>
      <Button size="small" variant="outlined" color="secondary" disabled={disabled || value <= 1}
        sx={styles.button} aria-label="Eine Person weniger" onClick={() => onChange(value - 1)}>−</Button>
      <Button size="small" variant="outlined" color="secondary" disabled={disabled || value >= MAX_PARTY_SIZE}
        sx={styles.button} aria-label="Eine Person mehr" onClick={() => onChange(value + 1)}>+</Button>
    </Box>
  )
}
