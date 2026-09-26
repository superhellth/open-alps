import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  list: { display: 'flex', flexDirection: 'column', gap: space.inline },
  candidateButton: { justifyContent: 'space-between', textTransform: 'none' },
} satisfies StyleMap
