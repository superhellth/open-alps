import type { SxProps, Theme } from '@mui/material/styles'

/** Shape of a `*.styles.ts` export: `sx` objects, or functions that build one from component state. */
export type StyleMap = Record<string, SxProps<Theme> | ((...args: never[]) => SxProps<Theme>)>
