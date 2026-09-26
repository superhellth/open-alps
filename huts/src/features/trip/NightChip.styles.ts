import type { StyleMap } from '@/ui/styleMap.js'
import { fontSize, rem, space, tokens } from '@/ui/tokens.js'

export const styles = {
  status: { display: 'inline-flex', alignItems: 'center', gap: space.inline, color: tokens.ink, fontWeight: 600 },
  icon: { fontSize: rem(fontSize.md) },
} satisfies StyleMap
