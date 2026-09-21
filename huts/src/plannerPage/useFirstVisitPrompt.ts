import { useCallback, useState } from 'react'
import { browserStorage } from '../trip/tripStorage.js'

const KEY = 'open-alps.prompt-seen'

/** The short "markers are start points" hint shown once per browser. */
export function useFirstVisitPrompt(storage: Pick<Storage, 'getItem' | 'setItem'> | null = browserStorage()) {
  const [visible, setVisible] = useState(() => {
    try { return storage?.getItem(KEY) !== '1' } catch { return true }
  })
  const dismiss = useCallback(() => {
    setVisible(false)
    try { storage?.setItem(KEY, '1') } catch { /* private window: the hint simply returns next visit */ }
  }, [storage])
  return { visible, dismiss }
}
