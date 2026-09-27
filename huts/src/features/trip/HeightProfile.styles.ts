import type { StyleMap } from '@/ui/styleMap.js'
import { PROFILE_HEIGHT } from './profileScale.js'

export const styles = {
  root: { width: '100%', '& svg': { display: 'block' } },
  caption: { display: 'block' },
  plot: { height: PROFILE_HEIGHT },
} satisfies StyleMap
