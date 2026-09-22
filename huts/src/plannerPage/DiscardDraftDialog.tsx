import { Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle } from '@mui/material'

export default function DiscardDraftDialog({ open, onDiscard, onCancel }: {
  open: boolean
  onDiscard: () => void
  onCancel: () => void
}) {
  return (
    <Dialog open={open} onClose={onCancel}>
      <DialogTitle>Entwurf verwerfen?</DialogTitle>
      <DialogContent>
        <DialogContentText>Der aktuell offene Entwurf wurde geändert und geht dabei verloren.</DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>Abbrechen</Button>
        <Button color="error" onClick={onDiscard}>Verwerfen</Button>
      </DialogActions>
    </Dialog>
  )
}
