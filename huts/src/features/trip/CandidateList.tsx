import { Box, Button, Typography } from '@mui/material'
import { formatSignpostTime } from '@/format/signpostTime.js'
import type { TripEditor } from './TripEditor.js'
import { styles } from './CandidateList.styles.js'

/** The candidates of the active edit (swap, extend, start, exit) as buttons, shown under the row that started the edit. */
export default function CandidateList({ editor, hutNameById, startLabel }: {
  editor: TripEditor
  hutNameById: Map<number, string>
  startLabel: (startId: number) => string
}) {
  const { editing, candidates } = editor
  if (!editing) return null
  const huts = editing.kind === 'swap' || editing.kind === 'extend'
  return (
    <Box sx={styles.list}>
      {candidates.length === 0 && <Typography variant="body2">{huts ? 'Keine passende Hütte im Wegenetz.' : 'Keine Alternative im Wegenetz.'}</Typography>}
      {candidates.map((c) => {
        const name = c.hutIndex !== undefined ? hutNameById.get(c.hutIndex) ?? String(c.hutIndex) : startLabel(c.startId!)
        const detail = c.legInH !== undefined
          ? `${formatSignpostTime(c.legInH)} · ${formatSignpostTime(c.legOutH ?? 0)}`
          : c.legH !== undefined ? formatSignpostTime(c.legH) : ''
        return (
          <Button
            key={c.hutIndex ?? c.startId} size="small" variant="outlined" color="secondary" sx={styles.candidateButton}
            onClick={() => editor.pickCandidate({ hutIndex: c.hutIndex, startId: c.startId })}
          >
            <span>{name}</span>
            <span>{detail}</span>
          </Button>
        )
      })}
      <Button size="small" onClick={editor.cancel}>Abbrechen</Button>
    </Box>
  )
}
