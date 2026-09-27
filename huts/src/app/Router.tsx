import AdminPage from '@/adminPage/AdminPage.js'
import { AppDataProvider } from '@/data/AppDataProvider.js'
import PlannerPage from '@/features/planner/PlannerPage.js'
import { SearchClientProvider } from '@/search/SearchClientProvider.js'
import { TripsProvider } from '@/trip/TripsProvider.js'
import { SHARE_HASH_PREFIX } from '@/trip/shareLink.js'
import { useHash } from '@/lib/useHash.js'

export default function Router() {
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
