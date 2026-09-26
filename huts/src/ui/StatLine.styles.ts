import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  root: { display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', columnGap: space.item, '& > *': { whiteSpace: 'nowrap' } },
} satisfies StyleMap
