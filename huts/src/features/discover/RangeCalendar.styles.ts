import type { SxProps, Theme } from '@mui/material/styles'
import { alpha } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { fontSize, opacity, rem, space, tokens } from '@/ui/tokens.js'

export const styles = {
  trigger: {
    textTransform: 'none', justifyContent: 'space-between', width: '100%', height: 40,
    fontSize: rem(fontSize.md), fontWeight: 400, color: 'text.primary', borderColor: alpha(tokens.ink, opacity.outline),
    '&:hover': { borderColor: 'text.primary' },
  },
  day: (state: { disabled: boolean; isEndpoint: boolean; inRange: boolean; isToday: boolean }): SxProps<Theme> => ({
    textAlign: 'center', py: space.inline, borderRadius: 1, cursor: state.disabled ? 'default' : 'pointer',
    bgcolor: state.isEndpoint ? 'primary.main' : state.inRange ? 'primary.light' : 'transparent',
    color: state.isEndpoint ? 'primary.contrastText' : 'text.primary',
    outline: state.isToday && !state.isEndpoint ? '1px solid' : 'none',
    outlineColor: 'primary.main',
    opacity: state.disabled ? 0.5 : 1,
    '&:hover': state.disabled ? undefined : { bgcolor: state.isEndpoint ? 'primary.main' : 'action.hover' },
  }),
  icon: { color: 'action.active' },
  popover: { width: 280, p: space.row },
  weekdayRow: { display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)' },
  monthHeader: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
} satisfies StyleMap
