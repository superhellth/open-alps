import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { AppData } from './buildAppData.js'
import { AppDataContext } from './appDataContext.js'
import type { AppDataState } from './appDataContext.js'
import { loadAppData } from './loadAppData.js'

export function AppDataProvider({ children, load = loadAppData }: { children: ReactNode; load?: () => Promise<AppData> }) {
  const [state, setState] = useState<AppDataState>({ status: 'loading' })
  useEffect(() => {
    let cancelled = false
    load().then(
      (data) => { if (!cancelled) setState({ status: 'ready', data }) },
      (e: Error) => { if (!cancelled) setState({ status: 'error', message: e.message }) },
    )
    return () => { cancelled = true }
  }, [load])
  return <AppDataContext.Provider value={state}>{children}</AppDataContext.Provider>
}
