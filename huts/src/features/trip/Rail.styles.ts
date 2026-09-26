import type { SxProps, Theme } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { space, tokens } from '@/ui/tokens.js'

const DOT = 12
/** Rail length above a dot: centers the dot on the first text line of a node. */
const DOT_OFFSET = 10

const segment = (visible: boolean, highlighted: boolean): SxProps<Theme> => ({
  width: highlighted ? '4px' : '2px',
  background: visible ? (highlighted ? tokens.signpost : tokens.ink) : 'transparent',
})

export const styles = {
  row: { display: 'grid', gridTemplateColumns: `${DOT + 4}px minmax(0, 1fr)`, columnGap: space.item },
  gutter: { display: 'flex', flexDirection: 'column', alignItems: 'center' },
  above: (visible: boolean): SxProps<Theme> => ({ ...segment(visible, false), height: `${DOT_OFFSET}px`, flexShrink: 0 }),
  below: (visible: boolean, highlighted: boolean): SxProps<Theme> => ({ ...segment(visible, highlighted), flex: 1 }),
  dot: (hollow: boolean): SxProps<Theme> => ({
    width: `${DOT}px`, height: `${DOT}px`, borderRadius: '50%', flexShrink: 0, boxSizing: 'border-box',
    border: `2px solid ${tokens.ink}`, background: hollow ? tokens.paper : tokens.ink,
  }),
  content: { display: 'flex', flexDirection: 'column', gap: space.inline, minWidth: 0 },
} satisfies StyleMap
