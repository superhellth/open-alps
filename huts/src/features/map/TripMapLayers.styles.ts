import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  statusBar: {
    position: 'absolute', top: 8, left: '50%', transform: 'translateX(-50%)', zIndex: 1000, bgcolor: 'background.paper',
    border: '1px solid', borderColor: 'divider', borderRadius: 1, px: space.row, py: space.inline, display: 'flex', gap: space.item, alignItems: 'center',
  },
} satisfies StyleMap
