import type { SxProps, Theme } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { SIGNPOST_FONT, tokens } from '@/ui/tokens.js'

const ARROW = 'polygon(0 0, calc(100% - 14px) 0, 100% 50%, calc(100% - 14px) 100%, 0 100%)'

export const styles = {
  plate: (outline: boolean): SxProps<Theme> => ({
    background: outline ? tokens.ink : tokens.signpost, clipPath: ARROW, p: outline ? '2px' : 0,
  }),
  plateInner: { background: tokens.paper, clipPath: ARROW },
  body: { px: 1.5, py: 1, pr: 3, fontFamily: SIGNPOST_FONT, color: tokens.ink },
  titleRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 2 },
  title: { fontWeight: 700, fontSize: '1.05rem' },
} satisfies StyleMap
