import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  root: { display: 'flex', flexDirection: 'column', gap: space.group },
  stages: { display: 'flex', flexDirection: 'column', gap: space.item },
  warnings: { display: 'flex', flexDirection: 'column', gap: space.item },
  heading: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  endLine: { display: 'flex', alignItems: 'center', gap: space.item, minHeight: '24px', px: space.item, py: space.inline },
  endLabel: { flex: 1, fontWeight: 600 },
  addButton: { alignSelf: 'flex-start', textTransform: 'none' },
} satisfies StyleMap
