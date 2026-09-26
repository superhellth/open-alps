import type { StyleMap } from '@/ui/styleMap.js'
import { fontSize, rem, space } from '@/ui/tokens.js'

export const styles = {
  root: { display: 'flex', flexDirection: 'column', gap: space.item },
  heading: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  rows: { display: 'flex', flexDirection: 'column', gap: space.item },
  endLine: { display: 'flex', alignItems: 'baseline', gap: space.item },
  endLabel: { flex: 1 },
  time: { fontWeight: 600 },
  meta: { display: 'flex', gap: space.item, color: 'text.secondary', fontSize: rem(fontSize.sm) },
  addButton: { alignSelf: 'flex-start', textTransform: 'none' },
} satisfies StyleMap
