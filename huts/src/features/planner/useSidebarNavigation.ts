import { useHash } from '@/lib/useHash.js'
import { useTrips } from '@/trip/tripsContext.js'

export type SidebarView = 'discover' | 'saved' | 'trip'

interface Options {
  mode: 'trip' | 'discover'
  openedFrom: 'results' | 'saved'
  setOpenedFrom: (from: 'results' | 'saved') => void
  /** Runs when the trip panel's back button is used, before the trip closes. */
  onBackFromTrip: () => void
}

/** Which sidebar view shows, and the hash/trip transitions between views. */
export function useSidebarNavigation({ mode, openedFrom, setOpenedFrom, onBackFromTrip }: Options) {
  const { dispatch, activeTrip } = useTrips()
  const hash = useHash()
  const sidebarView: SidebarView = mode === 'trip' ? 'trip' : (hash === '#trips' ? 'saved' : 'discover')

  function goPlanen() { window.location.hash = '' }
  function goMeineTouren() {
    if (activeTrip) dispatch({ type: 'closeActive' })
    window.location.hash = '#trips'
  }
  function goHome() {
    dispatch({ type: 'closeActive' })
    window.location.hash = ''
  }
  function openSavedTrip(id: string) {
    setOpenedFrom('saved')
    dispatch({ type: 'setActive', id })
  }
  function openPinnedDraft() {
    setOpenedFrom('saved')
    dispatch({ type: 'reopenDraft' })
  }
  function backFromTrip() {
    onBackFromTrip()
    dispatch({ type: 'closeActive' })
    if (openedFrom === 'saved') window.location.hash = '#trips'
  }

  return { sidebarView, goPlanen, goMeineTouren, goHome, openSavedTrip, openPinnedDraft, backFromTrip }
}
