import type { SxProps, Theme } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { fontSize, rem, SIGNPOST_FONT, space, tokens } from '@/ui/tokens.js'

const RIGHT_TIP = 'polygon(0 0, calc(100% - 9px) 0, 100% 50%, calc(100% - 9px) 100%, 0 100%)'

export const styles = {
  fingerpost: (isFirst: boolean, zIndex: number): SxProps<Theme> => ({
    position: 'relative', zIndex,
    marginLeft: isFirst ? 0 : '-9px', // design-exempt: fingerpost tip geometry
  }),
  fingerpostRing: (isFirst: boolean): SxProps<Theme> => ({
    position: 'absolute',
    top: -2,
    bottom: -2,
    left: isFirst ? -2 : 0,
    right: -2,
    backgroundColor: tokens.ink,
    clipPath: RIGHT_TIP,
  }),
  fingerpostLink: (active: boolean, isFirst: boolean): SxProps<Theme> => ({
    position: 'relative',
    display: 'block',
    fontFamily: SIGNPOST_FONT,
    fontWeight: 600,
    fontSize: rem(fontSize.md),
    textDecoration: 'none',
    color: active ? tokens.paper : tokens.ink,
    backgroundColor: active ? tokens.ink : tokens.paper,
    padding: isFirst ? '6px 22px 6px 16px' : '6px 22px 6px 25px', // design-exempt: fingerpost tip geometry
    clipPath: RIGHT_TIP,
    transition: 'color 120ms ease, background-color 120ms ease',
    '&:hover': active ? undefined : { backgroundColor: tokens.signpost },
  }),
  root: { display: 'flex', alignItems: 'center', gap: space.group, height: 48, flexShrink: 0, px: space.inset, borderBottom: `2px solid ${tokens.ink}` },
  wordmark: { fontFamily: SIGNPOST_FONT, fontWeight: 600, fontSize: rem(fontSize.lg), color: tokens.ink, textDecoration: 'none', flexShrink: 0 },
  nav: {
    display: 'flex',
    marginLeft: 'auto', // design-exempt: pushes the nav to the right edge
  },
} satisfies StyleMap
