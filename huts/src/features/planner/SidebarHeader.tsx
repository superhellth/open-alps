import { Box } from '@mui/material'
import { styles } from './SidebarHeader.styles.js'

export interface SidebarHeaderProps {
  view: 'discover' | 'saved' | 'trip'
  savedCount: number
  onWordmark: () => void
  onPlanen: () => void
  onMeineTouren: () => void
}

// Flat left edge, pointed right tip — every fingerpost uses this same shape, so all of them
// point right and none of them.

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
    <Box sx={styles.fingerpost(isFirst, total - index)}>
      <Box
        aria-hidden
        sx={styles.fingerpostRing(isFirst)}
      />
      <Box
        component="a"
        href="#"
        role="link"
        aria-current={active ? 'page' : undefined}
        onClick={(e: React.MouseEvent) => { e.preventDefault(); onClick() }}
        sx={styles.fingerpostLink(active, isFirst)}
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
    <Box sx={styles.root}>
      <Box
        component="a" href="#" onClick={(e: React.MouseEvent) => { e.preventDefault(); onWordmark() }}
        sx={styles.wordmark}
      >
        Hüttentouren
      </Box>
      <Box component="nav" sx={styles.nav}>
        {fingerpost('Planen', planenActive, 0, 2, onPlanen)}
        {fingerpost(`Meine Touren (${savedCount})`, !planenActive, 1, 2, onMeineTouren)}
      </Box>
    </Box>
  )
}
