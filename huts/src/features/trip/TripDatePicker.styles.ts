import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  legend: { display: 'flex', flexWrap: 'wrap', columnGap: space.item },
  /** An availability icon followed by its text on one line. */
  iconText: { display: 'inline-flex', alignItems: 'center', gap: space.inline },
  /** A night's icon under a calendar day number. */
  dayIcon: { display: 'inline-flex' },
} satisfies StyleMap
