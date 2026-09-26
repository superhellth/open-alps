import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  root: { display: 'flex', flexDirection: 'column', gap: space.item },
  topRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  actions: { display: 'flex', gap: space.item },
  twoColumns: { display: 'flex', gap: space.group },
  dateColumn: { flex: 1, minWidth: 0 },
} satisfies StyleMap
