import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  list: { display: 'flex', flexDirection: 'column', gap: space.group },
  stage: { display: 'flex', flexDirection: 'column', gap: space.inline },
  nightDetails: { display: 'flex', flexDirection: 'column', gap: space.item },
  statusGroup: { alignSelf: 'flex-start' },
  statusButton: { textTransform: 'none', py: space.inline },
} satisfies StyleMap
