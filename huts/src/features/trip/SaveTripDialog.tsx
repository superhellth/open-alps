import { useState } from 'react'
import { Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, TextField } from '@mui/material'
import { styles } from './SaveTripDialog.styles.js'

/** Asks for the tour's name before it is saved to Meine Touren. */
export default function SaveTripDialog({ open, initialName, onSave, onCancel }: {
  open: boolean
  initialName: string
  onSave: (name: string) => void
  onCancel: () => void
}) {
  const [name, setName] = useState(initialName)
  const trimmed = name.trim()
  function submit() { if (trimmed !== '') onSave(trimmed) }
  return (
    <Dialog
      open={open} onClose={onCancel} maxWidth="xs" fullWidth
      slotProps={{ transition: { onEnter: () => setName(initialName) } }}
    >
      <DialogTitle>Tour merken</DialogTitle>
      <DialogContent sx={styles.content}>
        <DialogContentText>Wird in „Meine Touren“ auf diesem Gerät gespeichert.</DialogContentText>
        <TextField
          autoFocus fullWidth size="small" label="Tourname" value={name}
          onChange={(e) => setName(e.target.value)}
          onFocus={(e) => e.target.select()}
          onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
        />
      </DialogContent>
      <DialogActions>
        <Button color="secondary" onClick={onCancel}>Abbrechen</Button>
        <Button variant="contained" disabled={trimmed === ''} onClick={submit}>Merken</Button>
      </DialogActions>
    </Dialog>
  )
}
