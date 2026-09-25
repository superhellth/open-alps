import type { StyleMap } from '@/ui/styleMap.js'

export const styles = {
  root: {
    position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)', zIndex: 1000, bgcolor: 'background.paper',
    border: '2px solid', borderColor: 'secondary.main', px: 2, py: 1, maxWidth: 420, pointerEvents: 'none',
  },
} satisfies StyleMap
