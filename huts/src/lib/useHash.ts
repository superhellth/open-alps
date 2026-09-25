import { useSyncExternalStore } from 'react'

function subscribe(callback: () => void) {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}

/** The current `window.location.hash` (including the leading `#`), re-rendering on change. */
export function useHash(): string {
  return useSyncExternalStore(subscribe, () => window.location.hash)
}
