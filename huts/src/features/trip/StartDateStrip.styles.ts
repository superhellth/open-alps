import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  root: { display: 'flex', flexDirection: 'column', gap: space.inline },
  header: { display: 'flex', gap: space.item, alignItems: 'center' },
  answers: { display: 'flex', gap: space.inline, flexWrap: 'wrap' },
} satisfies StyleMap
