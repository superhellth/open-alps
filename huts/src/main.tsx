import { StrictMode, useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import './index.css'
import theme from './theme.js'
import App from './App.js'
import GraphPage from './GraphPage.js'
import TourSearchPage from './TourSearchPage.js'

function subscribeHash(callback: () => void) {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}

function Router() {
  const hash = useSyncExternalStore(subscribeHash, () => window.location.hash)
  if (hash === '#graph') return <GraphPage />
  if (hash === '#tours') return <TourSearchPage />
  return <App />
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
