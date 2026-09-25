import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import './index.css'
import '@fontsource/barlow/400.css'
import '@fontsource/barlow/600.css'
import '@fontsource/barlow-semi-condensed/500.css'
import '@fontsource/barlow-semi-condensed/700.css'
import theme from '@/ui/theme.js'
import AdminPage from '@/adminPage/AdminPage.js'
import { AppDataProvider } from '@/data/AppDataProvider.js'
import PlannerPage from '@/plannerPage/PlannerPage.js'
import { SearchClientProvider } from '@/search/SearchClientProvider.js'
import { TripsProvider } from '@/trip/TripsProvider.js'
import { SHARE_HASH_PREFIX } from '@/trip/shareLink.js'
import { useHash } from '@/lib/useHash.js'

function Router() {
  const hash = useHash()
  // #admin needs none of the planner's data or the search worker, so it renders outside the providers.
  if (hash === '#admin') return <AdminPage />
  // Planen and Meine Touren share one provider instance, so switching tabs reloads and reparses nothing.
  // PlannerPage itself reads #trips internally to select its `saved` sidebar view.
  return (
    <AppDataProvider>
      <SearchClientProvider>
        <TripsProvider>
          <PlannerPage importHash={hash.startsWith(SHARE_HASH_PREFIX) ? hash : null} />
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
