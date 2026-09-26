import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  root: { p: space.inset, display: 'flex', flexDirection: 'column', gap: space.section },
} satisfies StyleMap
