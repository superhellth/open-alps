import { StrictMode, useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import './index.css'
import '@fontsource/barlow/400.css'
import '@fontsource/barlow/600.css'
import '@fontsource/barlow-semi-condensed/500.css'
import '@fontsource/barlow-semi-condensed/700.css'
import theme from './theme.js'
import AdminPage from './adminPage/AdminPage.js'
import AppShell from './AppShell.js'
import { AppDataProvider } from './data/AppDataProvider.js'
import PlannerPage from './plannerPage/PlannerPage.js'
import TripsPage from './plannerPage/TripsPage.js'
import { SearchClientProvider } from './search/SearchClientProvider.js'
import { TripsProvider } from './trip/TripsProvider.js'
import { SHARE_HASH_PREFIX } from './trip/shareLink.js'

function subscribeHash(callback: () => void) {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}

function Router() {
  const hash = useSyncExternalStore(subscribeHash, () => window.location.hash)
  // #admin needs none of the planner's data or the search worker, so it renders outside the providers.
  if (hash === '#admin') return <AdminPage />
  // Planen and Meine Touren share one provider instance, so switching tabs reloads and reparses nothing.
  return (
    <AppDataProvider>
      <SearchClientProvider>
        <TripsProvider>
          {hash === '#trips'
            ? <AppShell title="Hüttentouren"><TripsPage /></AppShell>
            : <PlannerPage importHash={hash.startsWith(SHARE_HASH_PREFIX) ? hash : null} />}
        </TripsProvider>
      </SearchClientProvider>
    </AppDataProvider>
  )
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
