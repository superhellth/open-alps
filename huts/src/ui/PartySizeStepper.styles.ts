import type { StyleMap } from './styleMap.js'
import { space } from './tokens.js'

export const styles = {
  row: { display: 'flex', gap: space.item, alignItems: 'center' },
  button: { width: 40, height: 40, minWidth: 0, p: 0 },
} satisfies StyleMap
