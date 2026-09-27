import { Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle } from '@mui/material'

export default function DiscardDraftDialog({ open, onDiscard, onCancel }: {
  open: boolean
  onDiscard: () => void
  onCancel: () => void
}) {
  return (
    <Dialog open={open} onClose={onCancel}>
      <DialogTitle>Ungespeicherte Tour verwerfen?</DialogTitle>
      <DialogContent>
        <DialogContentText>Die offene Tour ist nicht gespeichert und wurde geändert. Die Änderungen gehen verloren.</DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button color="secondary" onClick={onCancel}>Abbrechen</Button>
        <Button variant="contained" color="error" onClick={onDiscard}>Verwerfen</Button>
      </DialogActions>
    </Dialog>
  )
}
