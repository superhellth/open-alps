import { Box } from '@mui/material'
import { SIGNPOST_FONT, tokens } from '@/ui/theme.js'

export interface SidebarHeaderProps {
  view: 'discover' | 'saved' | 'trip'
  savedCount: number
  onWordmark: () => void
  onPlanen: () => void
  onMeineTouren: () => void
}

// Flat left edge, pointed right tip — every fingerpost uses this same shape, so all of them
// point right and none of them.
const RIGHT_TIP = 'polygon(0 0, calc(100% - 9px) 0, 100% 50%, calc(100% - 9px) 100%, 0 100%)'

// Each fingerpost after the first overlaps the previous one by the tip depth (marginLeft -9px)
// and sits underneath it (lower z-index), so the earlier fingerpost's point paints over the
// later one's flat left corner. Outside that point — above and below it, where the earlier
// shape's diagonal has already tapered away — the later fingerpost's own flat rectangle shows
// through and fills the gap, keeping the top/bottom edge one continuous straight line.
//
// A border on a clip-path shape only strokes the box's straight edges — clip-path crops the
// border away along the diagonal cut, leaving the point outline-less. The fix is a second,
// slightly larger copy of the same shape behind it in ink, acting as a 2px stroke ring.
function fingerpost(label: string, active: boolean, index: number, total: number, onClick: () => void) {
  const isFirst = index === 0
  return (
    <Box sx={{ position: 'relative', marginLeft: isFirst ? 0 : '-9px', zIndex: total - index }}>
      <Box
        aria-hidden
        sx={{
          position: 'absolute',
          top: -2,
          bottom: -2,
          left: isFirst ? -2 : 0,
          right: -2,
          backgroundColor: tokens.ink,
          clipPath: RIGHT_TIP,
        }}
      />
      <Box
        component="a"
        href="#"
        role="link"
        aria-current={active ? 'page' : undefined}
        onClick={(e: React.MouseEvent) => { e.preventDefault(); onClick() }}
        sx={{
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
        }}
      >
        {label}
      </Box>
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
        {fingerpost('Planen', planenActive, 0, 2, onPlanen)}
        {fingerpost(`Meine Touren (${savedCount})`, !planenActive, 1, 2, onMeineTouren)}
      </Box>
    </Box>
  )
}
