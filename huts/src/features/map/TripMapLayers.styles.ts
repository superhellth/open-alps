import type { StyleMap } from '@/ui/styleMap.js'

export const styles = {
  statusBar: {
    position: 'absolute', top: 8, left: '50%', transform: 'translateX(-50%)', zIndex: 1000, bgcolor: 'background.paper',
    border: '1px solid', borderColor: 'divider', borderRadius: 1, px: 1.5, py: 0.5, display: 'flex', gap: 1, alignItems: 'center',
  },
} satisfies StyleMap
