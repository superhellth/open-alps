import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { CssBaseline, ThemeProvider } from '@mui/material'
import theme from '../theme.js'
import EditorApp from './EditorApp.js'

const container = document.getElementById('root')
if (!container) throw new Error('gpxEditor/main.tsx: #root element not found')

createRoot(container).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <EditorApp />
    </ThemeProvider>
  </StrictMode>,
)
