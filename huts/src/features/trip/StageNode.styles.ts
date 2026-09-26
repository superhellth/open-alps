import type { SxProps, Theme } from '@mui/material/styles'
import { alpha } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { fontSize, opacity, rem, space, tokens } from '@/ui/tokens.js'

export const styles = {
  root: { display: 'flex', flexDirection: 'column', gap: space.item },
  head: { display: 'flex', alignItems: 'center', gap: space.item },
  /** The clickable face of a night: the whole name and state block toggles its booking detail. */
  toggle: {
    flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: space.item, justifyContent: 'flex-start',
    textAlign: 'left', px: space.item, py: space.inline, borderRadius: 1,
    '&:hover, &.Mui-focusVisible': { background: alpha(tokens.ink, opacity.hoverTint) },
  },
  face: { flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', px: space.item, py: space.inline },
  text: { flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' },
  titleLine: { display: 'flex', alignItems: 'baseline', gap: space.item },
  number: { fontWeight: 700, color: 'text.secondary' },
  title: { fontWeight: 700, fontSize: rem(fontSize.md), overflowWrap: 'anywhere' },
  meta: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: space.item, color: 'text.secondary', fontSize: rem(fontSize.sm) },
  chevron: (expanded: boolean): SxProps<Theme> => ({ transition: 'transform 150ms', transform: expanded ? 'rotate(180deg)' : 'none' }),
  detail: { px: space.item },
} satisfies StyleMap
