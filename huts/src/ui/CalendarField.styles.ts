import { alpha } from '@mui/material/styles'
import type { StyleMap } from './styleMap.js'
import { fontSize, opacity, rem, space, tokens } from './tokens.js'

export const styles = {
  trigger: {
    textTransform: 'none', justifyContent: 'space-between', width: '100%', height: 40,
    fontSize: rem(fontSize.md), fontWeight: 400, color: 'text.primary', borderColor: alpha(tokens.ink, opacity.outline),
    '&:hover': { borderColor: 'text.primary' },
  },
  icon: { color: 'action.active' },
  popover: { width: 280, p: space.row, display: 'flex', flexDirection: 'column', gap: space.item },
} satisfies StyleMap
