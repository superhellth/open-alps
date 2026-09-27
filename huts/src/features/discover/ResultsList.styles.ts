import type { SxProps, Theme } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { SIGNPOST_FONT, space, tokens } from '@/ui/tokens.js'

export const styles = {
  noMatches: { p: space.inset, display: 'flex', flexDirection: 'column', gap: space.item, alignItems: 'flex-start' },
  sortBar: {
    display: 'flex', alignItems: 'center', justifyContent: 'center', flexWrap: 'wrap',
    p: space.inset, gap: space.item, position: 'sticky', top: 0, zIndex: 1,
    bgcolor: 'background.paper', borderBottom: '1px solid', borderColor: 'divider',
  },
  sortChipLabel: { display: 'flex', alignItems: 'center', gap: space.inline, fontFamily: SIGNPOST_FONT, fontWeight: 600 },
  sortChip: (active: boolean): SxProps<Theme> => (active
    ? { bgcolor: tokens.signpost, color: tokens.ink, '&:hover': { bgcolor: tokens.signpost } }
    : { bgcolor: 'transparent', border: '1px solid', borderColor: 'divider' }),
  row: (highlighted: boolean): SxProps<Theme> => {
    const active = { bgcolor: `color-mix(in srgb, ${tokens.signpost} 25%, transparent)`, boxShadow: `inset 4px 0 0 ${tokens.signpost}` }
    return {
      display: 'flex', flexDirection: 'column', alignItems: 'stretch', gap: space.inline, borderBottom: '1px solid', borderColor: 'divider',
      '&:hover, &.Mui-focusVisible': active,
      ...(highlighted && active),
    }
  },
  chainRow: { display: 'flex', alignItems: 'baseline', gap: space.item, fontFamily: SIGNPOST_FONT, fontWeight: 600 },
  statRow: { color: 'text.secondary' },
  showAll: { px: space.item, pt: space.item },
  emptyHint: { p: space.inset },
  list: { px: space.inset, pb: space.inset },
  pagination: { px: space.inset, pb: space.inset },
  sortArrow: { fontSize: 'inherit' },
} satisfies StyleMap
