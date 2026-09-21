import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Box, Slider, Typography } from '@mui/material'

export default function DraftRangeSlider({ label, value, onCommit, min, max, step, disabled, format, note }: {
  label: string
  value: [number, number]
  onCommit: (v: [number, number]) => void
  min: number
  max: number
  step: number
  disabled?: boolean
  format: (v: [number, number]) => string
  note?: (draft: [number, number]) => ReactNode
}) {
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])
  return (
    <Box>
      <Typography variant="subtitle2">{label}: {format(draft)}</Typography>
      <Slider
        size="small" value={draft} min={min} max={max} step={step} disabled={disabled} valueLabelDisplay="auto"
        onChange={(_e, v) => setDraft(v as [number, number])}
        onChangeCommitted={(_e, v) => onCommit(v as [number, number])}
        aria-label={label}
      />
      {note?.(draft)}
    </Box>
  )
}
