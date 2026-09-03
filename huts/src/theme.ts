import { createTheme } from '@mui/material/styles'

// Single source of truth for palette/spacing/typography (spec D). No dark-mode requirement
// today, but nothing here precludes adding a dark palette variant later.
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#1b5e20' }, // matches the existing map header green
    secondary: { main: '#e65100' }, // matches AdminPage's edge-orange accent
  },
  typography: {
    fontFamily: 'system-ui, sans-serif',
  },
})

export default theme
