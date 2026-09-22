import { Box } from '@mui/material'
import { SIGNPOST_FONT, tokens } from '../theme.js'

export interface SidebarHeaderProps {
  view: 'discover' | 'saved' | 'trip'
  savedCount: number
  onWordmark: () => void
  onPlanen: () => void
  onMeineTouren: () => void
}

function fingerpost(label: string, active: boolean, isFirst: boolean, onClick: () => void) {
  return (
    <Box
      component="a"
      href="#"
      role="link"
      aria-current={active ? 'page' : undefined}
      onClick={(e: React.MouseEvent) => { e.preventDefault(); onClick() }}
      sx={{
        fontFamily: SIGNPOST_FONT,
        fontWeight: 600,
        fontSize: '0.95rem',
        textDecoration: 'none',
        color: active ? tokens.paper : tokens.ink,
        backgroundColor: active ? tokens.ink : 'transparent',
        border: `2px solid ${tokens.ink}`,
        borderLeftWidth: isFirst ? 2 : 0,
        padding: '6px 22px 6px 16px',
        clipPath: 'polygon(0 0, calc(100% - 9px) 0, 100% 50%, calc(100% - 9px) 100%, 0 100%)',
        marginRight: '-9px',
        transition: 'color 120ms ease, background-color 120ms ease',
        '&:hover': active ? undefined : { backgroundColor: 'rgba(35, 39, 43, 0.08)' },
      }}
    >
      {label}
    </Box>
  )
}

// The app bar is gone (the map owns the full viewport height); this row replaces it inside the
// 420px sidebar. Planen covers both discover and trip — trip is a stage of planning, not a
// separate destination — so only Meine Touren gets its own active state.
export default function SidebarHeader({ view, savedCount, onWordmark, onPlanen, onMeineTouren }: SidebarHeaderProps) {
  const planenActive = view !== 'saved'
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, height: 48, flexShrink: 0, px: 2, borderBottom: `2px solid ${tokens.ink}` }}>
      <Box
        component="a" href="#" onClick={(e: React.MouseEvent) => { e.preventDefault(); onWordmark() }}
        sx={{ fontFamily: SIGNPOST_FONT, fontWeight: 600, fontSize: '1.1rem', color: tokens.ink, textDecoration: 'none', flexShrink: 0 }}
      >
        Hüttentouren
      </Box>
      <Box component="nav" sx={{ display: 'flex', marginLeft: 'auto' }}>
        {fingerpost('Planen', planenActive, true, onPlanen)}
        {fingerpost(`Meine Touren (${savedCount})`, !planenActive, false, onMeineTouren)}
      </Box>
    </Box>
  )
}
