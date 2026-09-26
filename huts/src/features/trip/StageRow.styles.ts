import type { SxProps, Theme } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { fontSize, rem, space, tokens } from '@/ui/tokens.js'

export const styles = {
  /** Plain row; the left bar turns signpost yellow while its leg is hovered anywhere. A changed night is outlined. */
  row: (highlighted: boolean, changed: boolean): SxProps<Theme> => ({
    display: 'flex', flexDirection: 'column', gap: space.inline, pl: space.item,
    borderLeft: `4px solid ${highlighted ? tokens.signpost : 'transparent'}`,
    ...(changed && { outline: `1px solid ${tokens.ink}` }),
  }),
  line: { display: 'flex', alignItems: 'baseline', gap: space.item },
  number: { fontWeight: 700 },
  title: { fontWeight: 700, flex: 1, fontSize: rem(fontSize.md) },
  time: { fontWeight: 600 },
  meta: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: space.item, color: 'text.secondary', fontSize: rem(fontSize.sm) },
} satisfies StyleMap
