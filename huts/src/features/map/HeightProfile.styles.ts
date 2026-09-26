import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  root: { width: '100%', bgcolor: 'background.paper' },
  message: { p: space.item },
  readout: { display: 'block', px: space.item, pt: space.inline },
} satisfies StyleMap
