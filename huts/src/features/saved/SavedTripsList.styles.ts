import type { SxProps, Theme } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  root: { p: space.inset, display: 'flex', flexDirection: 'column', gap: space.group },
  header: { display: 'flex', gap: space.item, alignItems: 'center' },
  tripRow: { display: 'flex', gap: space.item, alignItems: 'center', py: space.row },
  tripBody: { flex: 1, cursor: 'pointer' },
  renameRow: { display: 'flex', gap: space.item },
  tripTitleRow: { display: 'flex', gap: space.item, alignItems: 'center' },
  draftRow: { py: space.row, borderBottom: '1px solid', borderColor: 'divider', cursor: 'pointer' },
  tripCard: (hovered: boolean): SxProps<Theme> => ({
    borderBottom: '1px solid', borderColor: 'divider', backgroundColor: hovered ? 'action.hover' : undefined,
  }),
  menuGlyph: { fontWeight: 700 },
  strong: { fontWeight: 600 },
} satisfies StyleMap
