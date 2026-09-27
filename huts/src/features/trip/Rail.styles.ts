import type { SxProps, Theme } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { STOP_SYMBOL_SIZE } from '@/ui/StopSymbol.js'
import { space, tokens } from '@/ui/tokens.js'

/** Centre of a node's first text line below the row top. */
const FIRST_LINE_CENTER = 16
/** Rail length above a stop symbol: centers the symbol on the first text line of a node. */
const SYMBOL_OFFSET = FIRST_LINE_CENTER - STOP_SYMBOL_SIZE / 2

const segment = (visible: boolean, highlighted: boolean): SxProps<Theme> => ({
  width: highlighted ? '4px' : '2px',
  background: visible ? (highlighted ? tokens.signpost : tokens.ink) : 'transparent',
})

export const styles = {
  row: { display: 'grid', gridTemplateColumns: `${STOP_SYMBOL_SIZE + 4}px minmax(0, 1fr)`, columnGap: space.item },
  gutter: { display: 'flex', flexDirection: 'column', alignItems: 'center' },
  above: (visible: boolean, highlighted: boolean): SxProps<Theme> => ({ ...segment(visible, highlighted), height: `${SYMBOL_OFFSET}px`, flexShrink: 0 }),
  below: (visible: boolean, highlighted: boolean): SxProps<Theme> => ({ ...segment(visible, highlighted), flex: 1 }),
  symbol: { display: 'flex', flexShrink: 0 },
  content: { display: 'flex', flexDirection: 'column', gap: space.inline, minWidth: 0 },
} satisfies StyleMap
