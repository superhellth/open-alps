import type { StyleMap } from '@/ui/styleMap.js'
import { fontSize, rem, space } from '@/ui/tokens.js'

export const styles = {
  root: { display: 'flex', flexDirection: 'column' },
  head: { display: 'flex', alignItems: 'center', gap: space.item },
  face: { flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', px: space.item, py: space.inline },
  titleLine: { display: 'flex', alignItems: 'baseline', gap: space.item },
  number: { fontWeight: 700, color: 'text.secondary' },
  title: { flex: 1, minWidth: 0, fontWeight: 700, fontSize: rem(fontSize.md), overflowWrap: 'anywhere' },
  date: { flexShrink: 0, color: 'text.secondary', fontSize: rem(fontSize.sm), whiteSpace: 'nowrap' },
  meta: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: space.item, color: 'text.secondary', fontSize: rem(fontSize.sm) },
  candidates: { px: space.item, pt: space.item },
} satisfies StyleMap
