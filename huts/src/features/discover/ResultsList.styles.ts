import type { SxProps, Theme } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { SIGNPOST_FONT, tokens } from '@/ui/tokens.js'

export const styles = {
  noMatches: { p: 2, display: 'flex', flexDirection: 'column', gap: 1, alignItems: 'flex-start' },
  sortBar: {
    display: 'flex', alignItems: 'center', justifyContent: 'center', flexWrap: 'wrap',
    p: 2, gap: 1, position: 'sticky', top: 0, zIndex: 1,
    bgcolor: 'background.paper', borderBottom: '1px solid', borderColor: 'divider',
  },
  sortChipLabel: { display: 'flex', alignItems: 'center', gap: 0.5, fontFamily: SIGNPOST_FONT, fontWeight: 600 },
  sortChip: (active: boolean): SxProps<Theme> => (active
    ? { bgcolor: tokens.signpost, color: tokens.ink, '&:hover': { bgcolor: tokens.signpost } }
    : { bgcolor: 'transparent', border: '1px solid', borderColor: 'divider' }),
  row: (highlighted: boolean): SxProps<Theme> => ({
    display: 'block', borderBottom: '1px solid', borderColor: 'divider',
    ...(highlighted && { bgcolor: `color-mix(in srgb, ${tokens.signpost} 25%, transparent)`, boxShadow: `inset 4px 0 0 ${tokens.signpost}` }),
  }),
  chainRow: { display: 'flex', alignItems: 'baseline', gap: 1, fontFamily: SIGNPOST_FONT, fontWeight: 600 },
  statRow: { display: 'flex', flexWrap: 'nowrap', gap: 2, mt: 0.5, color: 'text.secondary' },
  officialRow: { display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 },
} satisfies StyleMap
