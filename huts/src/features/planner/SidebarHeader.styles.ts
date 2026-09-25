import type { SxProps, Theme } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { SIGNPOST_FONT, tokens } from '@/ui/tokens.js'

const RIGHT_TIP = 'polygon(0 0, calc(100% - 9px) 0, 100% 50%, calc(100% - 9px) 100%, 0 100%)'

export const styles = {
  fingerpost: (isFirst: boolean, zIndex: number): SxProps<Theme> => ({
    position: 'relative', marginLeft: isFirst ? 0 : '-9px', zIndex,
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
    fontSize: '0.95rem',
    textDecoration: 'none',
    color: active ? tokens.paper : tokens.ink,
    backgroundColor: active ? tokens.ink : tokens.paper,
    padding: isFirst ? '6px 22px 6px 16px' : '6px 22px 6px 25px',
    clipPath: RIGHT_TIP,
    transition: 'color 120ms ease, background-color 120ms ease',
    '&:hover': active ? undefined : { backgroundColor: tokens.signpost },
  }),
  root: { display: 'flex', alignItems: 'center', gap: 2, height: 48, flexShrink: 0, px: 2, borderBottom: `2px solid ${tokens.ink}` },
  wordmark: { fontFamily: SIGNPOST_FONT, fontWeight: 600, fontSize: '1.1rem', color: tokens.ink, textDecoration: 'none', flexShrink: 0 },
} satisfies StyleMap
