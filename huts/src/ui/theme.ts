import { alpha, createTheme } from '@mui/material/styles'
import { SIGNPOST_FONT, tokens } from './tokens.js'

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
    fontFamily: '"Barlow", system-ui, sans-serif',
    h6: { fontFamily: SIGNPOST_FONT, fontWeight: 600 },
    subtitle2: { fontFamily: SIGNPOST_FONT, fontWeight: 600 },
  },
  components: {
    MuiAppBar: {
      defaultProps: { color: 'default', elevation: 0 },
      styleOverrides: { root: { backgroundColor: tokens.paper, color: tokens.ink, borderBottom: `2px solid ${tokens.ink}` } },
    },
    MuiPaper: { defaultProps: { elevation: 0 } },
    MuiTabs: { styleOverrides: { indicator: { backgroundColor: tokens.signpost, height: 4 } } },
    MuiTab: {
      styleOverrides: {
        root: {
          backgroundColor: alpha(tokens.ink, 0.05),
          '&:hover': { backgroundColor: alpha(tokens.ink, 0.09) },
          '&:not(.Mui-selected)': { color: alpha(tokens.ink, 0.6) },
          '&.Mui-selected': { backgroundColor: tokens.paper },
        },
      },
    },
  },
})

export default theme
