import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  chips: { display: 'flex', gap: space.inline },
  chip: { flex: 1, minWidth: 0, textTransform: 'none', flexDirection: 'column', lineHeight: 1.2, px: space.inline },
} satisfies StyleMap
