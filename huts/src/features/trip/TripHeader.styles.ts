import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  root: { display: 'flex', flexDirection: 'column', gap: space.item },
  topRow: { display: 'flex', justifyContent: 'space-between' },
  draftRow: { display: 'flex', gap: space.item, alignItems: 'center' },
  titleButton: { background: 'none', border: 0, p: 0, font: 'inherit', color: 'inherit', cursor: 'pointer', textAlign: 'left' },
  titleInput: { flex: 1 },
} satisfies StyleMap
