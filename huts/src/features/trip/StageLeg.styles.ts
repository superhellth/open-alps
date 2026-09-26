import type { SxProps, Theme } from '@mui/material/styles'
import { alpha } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { fontSize, opacity, rem, SIGNPOST_FONT, space, tokens } from '@/ui/tokens.js'

export const styles = {
  /** The hover target of one leg, rail included; tinted while its leg is highlighted anywhere. */
  root: (highlighted: boolean): SxProps<Theme> => ({
    borderRadius: 1,
    background: highlighted ? alpha(tokens.ink, opacity.hoverTint) : 'transparent',
  }),
  line: { py: space.item, px: space.item, display: 'flex', alignItems: 'baseline', gap: space.item, flexWrap: 'wrap', fontFamily: SIGNPOST_FONT, color: tokens.ink },
  time: { fontWeight: 600 },
  stats: { color: 'text.secondary', fontSize: rem(fontSize.sm) },
} satisfies StyleMap
