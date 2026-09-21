import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { createSearchClient } from './searchClient.js'
import type { SearchClient, WorkerLike } from './searchClient.js'
import { makeSearchWorker } from './makeSearchWorker.js'

const SearchClientContext = createContext<SearchClient | null>(null)

export function SearchClientProvider({ children, makeWorker = makeSearchWorker }: { children: ReactNode; makeWorker?: () => WorkerLike }) {
  const [client, setClient] = useState<SearchClient | null>(null)
  useEffect(() => {
    const created = createSearchClient(makeWorker)
    setClient(created)
    return () => created.dispose()
  }, [makeWorker])
  return <SearchClientContext.Provider value={client}>{children}</SearchClientContext.Provider>
}

export function useSearchClient(): SearchClient | null {
  return useContext(SearchClientContext)
}
