import { useEffect, useState } from 'react'
import { Box, Slider, Typography } from '@mui/material'

// Owns its own drag-in-progress value so the Slider's continuous onChange events (fired on every
// pointer move) only re-render this small subtree, not the whole page's form + result panes —
// the parent form state is only touched once, via onChangeCommitted, on release.
function LegTimeSlider({
  value, onCommit,
}: {
  value: [number, number]
  onCommit: (v: [number, number]) => void
}) {
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])

  return (
    <Box>
      <Typography variant="subtitle2">
        Gehzeit pro Etappe: {draft[0]}–{draft[1]}h
      </Typography>
      <Slider
        value={draft}
        onChange={(_e, v) => setDraft(v as [number, number])}
        onChangeCommitted={(_e, v) => onCommit(v as [number, number])}
        min={0}
        max={12}
        step={0.5}
        marks
        valueLabelDisplay="auto"
      />
    </Box>
  )
}

export default LegTimeSlider
