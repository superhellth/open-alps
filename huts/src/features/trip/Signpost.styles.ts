import type { SxProps, Theme } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { fontSize, rem, SIGNPOST_FONT, space, tokens } from '@/ui/tokens.js'

const ARROW = 'polygon(0 0, calc(100% - 14px) 0, 100% 50%, calc(100% - 14px) 100%, 0 100%)'

export const styles = {
  plate: (outline: boolean): SxProps<Theme> => ({
    background: outline ? tokens.ink : tokens.signpost, clipPath: ARROW, p: outline ? '2px' : 0,
  }),
  plateInner: { background: tokens.paper, clipPath: ARROW },
  body: { display: 'flex', flexDirection: 'column', gap: space.inline, px: space.row, py: space.item, pr: space.section, fontFamily: SIGNPOST_FONT, color: tokens.ink },
  titleRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: space.item },
  stats: { fontSize: rem(fontSize.sm), display: 'flex', gap: space.item },
  title: { fontWeight: 700, fontSize: rem(fontSize.lg) },
} satisfies StyleMap
