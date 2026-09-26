import type { SxProps, Theme } from '@mui/material/styles'
import type { StyleMap } from './styleMap.js'
import { fontSize, opacity, rem, space } from './tokens.js'

export const styles = {
  day: (state: { disabled: boolean; isEndpoint: boolean; inRange: boolean; isToday: boolean }): SxProps<Theme> => ({
    textAlign: 'center', py: space.inline, borderRadius: 1, cursor: state.disabled ? 'default' : 'pointer',
    bgcolor: state.isEndpoint ? 'primary.main' : state.inRange ? 'primary.light' : 'transparent',
    color: state.isEndpoint ? 'primary.contrastText' : 'text.primary',
    outline: state.isToday && !state.isEndpoint ? '1px solid' : 'none',
    outlineColor: 'primary.main',
    opacity: state.disabled ? opacity.dimmed : 1,
    '&:hover': state.disabled ? undefined : { bgcolor: state.isEndpoint ? 'primary.main' : 'action.hover' },
  }),
  mark: { fontSize: rem(fontSize.xs), lineHeight: 1, minHeight: rem(fontSize.xs) },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)' },
  monthHeader: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  monthLabel: { textTransform: 'capitalize' },
} satisfies StyleMap
