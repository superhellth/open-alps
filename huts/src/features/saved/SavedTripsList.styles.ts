import type { SxProps, Theme } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'

export const styles = {
  draftRow: { py: 1.5, borderBottom: '1px solid', borderColor: 'divider', cursor: 'pointer' },
  tripCard: (hovered: boolean): SxProps<Theme> => ({
    borderBottom: '1px solid', borderColor: 'divider', backgroundColor: hovered ? 'action.hover' : undefined,
  }),
  menuGlyph: { fontWeight: 700 },
  strong: { fontWeight: 600 },
} satisfies StyleMap
