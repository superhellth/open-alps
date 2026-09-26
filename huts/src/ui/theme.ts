import { alpha, createTheme } from '@mui/material/styles'
import { fontSize, fonts, opacity, rem, SIGNPOST_FONT, space, tokens } from './tokens.js'

export { tokens, SIGNPOST_FONT }

// Light panels in map-paper tones; the signpost yellow is the only accent and is only ever a fill
// with ink text on it. No shadows, cards or gradients.
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: tokens.signpost, contrastText: tokens.ink },
    secondary: { main: tokens.ink, contrastText: tokens.paper },
    background: { default: tokens.paper, paper: tokens.paper },
    text: { primary: tokens.ink },
  },
  shape: { borderRadius: 2 },
  typography: {
    fontFamily: fonts.body,
    h6: { fontFamily: fonts.signpost, fontWeight: 600, fontSize: rem(fontSize.xl) },
    subtitle2: { fontFamily: fonts.signpost, fontWeight: 600, fontSize: rem(fontSize.sm) },
    body1: { fontSize: rem(fontSize.md) },
    body2: { fontSize: rem(fontSize.sm) },
    caption: { fontSize: rem(fontSize.xs) },
  },
  components: {
    MuiAppBar: {
      defaultProps: { color: 'default', elevation: 0 },
      styleOverrides: { root: { backgroundColor: tokens.paper, color: tokens.ink, borderBottom: `2px solid ${tokens.ink}` } },
    },
    MuiPaper: { defaultProps: { elevation: 0 } },
    // Buttons share the title's and content's inset instead of MUI's tighter default.
    MuiDialogActions: { styleOverrides: { root: ({ theme }) => ({ padding: theme.spacing(0, space.section, space.section) }) } },
    MuiTabs: { styleOverrides: { indicator: { backgroundColor: tokens.signpost, height: 4 } } },
    MuiTab: {
      styleOverrides: {
        root: {
          backgroundColor: alpha(tokens.ink, opacity.hoverTint),
          '&:hover': { backgroundColor: alpha(tokens.ink, opacity.hoverTintStrong) },
          '&:not(.Mui-selected)': { color: alpha(tokens.ink, opacity.muted) },
          '&.Mui-selected': { backgroundColor: tokens.paper },
        },
      },
    },
  },
})

export default theme
