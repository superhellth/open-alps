import { StrictMode, useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import './index.css'
import theme from './theme.js'
import AdminPage from './adminPage/AdminPage.js'
import TourSearchPage from './tourSearchPage/TourSearchPage.js'

function subscribeHash(callback: () => void) {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}

function Router() {
  const hash = useSyncExternalStore(subscribeHash, () => window.location.hash)
  if (hash === '#admin') return <AdminPage />
  return <TourSearchPage />
}

const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('#root element not found')

createRoot(rootElement).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Router />
    </ThemeProvider>
  </StrictMode>,
)
