import { useEffect, useState } from 'react'
import { Alert, Box, Slider, Typography } from '@mui/material'
import { LEG_COUNT_SLOW_WARNING_THRESHOLD } from './helpers.js'

// Owns its own drag-in-progress value so the Slider's continuous onChange events (fired on every
// pointer move) only re-render this small subtree, not the whole page's form + result panes —
// the parent form state is only touched once, via onChangeCommitted, on release.
function LegCountSlider({
  value, onCommit,
}: {
  value: [number, number]
  onCommit: (v: [number, number]) => void
}) {
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])
  const tooHigh = draft[1] > LEG_COUNT_SLOW_WARNING_THRESHOLD

  return (
    <Box>
      <Typography variant="subtitle2">
        Etappen: {draft[0]}–{draft[1]}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {draft[1]} Etappen = {draft[1] - 1} Übernachtungen
      </Typography>
      <Slider
        value={draft}
        onChange={(_e, v) => setDraft(v as [number, number])}
        onChangeCommitted={(_e, v) => onCommit(v as [number, number])}
        min={1}
        max={14}
        step={1}
        marks
        valueLabelDisplay="auto"
      />
      {tooHigh && (
        <Alert severity="warning" sx={{ mt: 1 }}>
          Hohe Etappenzahl kann die Suche spürbar verlangsamen.
        </Alert>
      )}
    </Box>
  )
}

export default LegCountSlider
